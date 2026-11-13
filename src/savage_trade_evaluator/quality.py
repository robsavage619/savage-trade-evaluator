"""Gates that decide whether a daily refresh may be published.

A re-ingest can succeed (exit 0, rows counted) and still leave the data wrong: a
frozen row, a club missing from a fetch, a source that quietly returned less. Each
gate looks at what the database holds after the ingests, not at what a command said.

Severity: ``fail`` blocks publishing and leaves the last good site serving;
``warn`` publishes but marks the refresh degraded (a source that is allowed to lag,
such as Spotrac contracts).
"""

# pyright: reportOptionalSubscript=false, reportGeneralTypeIssues=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb

REGRESSION_FLOOR = 0.9  # a current-season table may not shrink below this share of last good
WAR_FLOOR = 0.99  # WAR only accumulates; allow rounding and small corrections
MAX_GAMES = 162
MIN_ROSTER = 25
TRANSACTION_MAX_AGE_DAYS = 7


@dataclass(frozen=True)
class Table:
    """A table holding the current season, and how much of it a refresh must touch.

    Attributes:
        name: Table name.
        season_col: Column holding the season.
        min_refreshed: Share of the season's rows that must carry a fresh ``ingested_at``.
        severity: ``fail`` or ``warn``.
        max_age_days: When set, the check is "no row older than this" instead of a share
            rewritten this run, for sources that refresh in rotation.
    """

    name: str
    season_col: str
    min_refreshed: float
    severity: str = "fail"
    max_age_days: int | None = None


# Savant leaderboards drop players below a minimum, so not every old row is rewritten.
CURRENT_TABLES: tuple[Table, ...] = (
    Table("bwar_batting", "year_id", 0.95),
    Table("bwar_pitching", "year_id", 0.95),
    Table("statcast_batting_expected", "year", 0.7),
    Table("statcast_pitching_expected", "year", 0.7),
    Table("statcast_pitcher_percentile_ranks", "year", 0.7),
    Table("statcast_batter_percentile_ranks", "year", 0.7),
    Table("statcast_pitcher_arsenal_stats", "year", 0.7),
    Table("statcast_outs_above_average", "year", 0.7),
    Table("statcast_sprint_speed", "year", 0.7),
    Table("statcast_batter_exitvelo_barrels", "year", 0.7),
    Table("statcast_pitch_movement", "year", 0.7),
    Table("standings", "season", 1.0),
    Table("team_season_stats", "season", 1.0),
    Table("spotrac_player_contracts", "season", 0.9, "warn"),
    Table("spotrac_team_payroll", "season", 0.9, "warn"),
    # Spotrac throttles with 403s partway through the per-player scrape, so the scrape
    # rotates (stalest first) and no single run rewrites every row: judge by age instead.
    Table("spotrac_contract_terms", "season", 0.0, "warn", max_age_days=7),
    Table("mlb_free_agents", "season", 0.5, "warn"),
)


@dataclass(frozen=True)
class Gate:
    """One check and its outcome."""

    name: str
    severity: str
    ok: bool
    detail: str


def overall(gates: list[Gate]) -> str:
    """``failed`` if any fail-gate failed, ``degraded`` if only warn-gates did, else ``ok``."""
    if any(not g.ok and g.severity == "fail" for g in gates):
        return "failed"
    return "degraded" if any(not g.ok for g in gates) else "ok"


def check_freshness(conn: duckdb.DuckDBPyConnection, season: int, since: datetime) -> list[Gate]:
    """Gates that the current season's rows were rewritten by this run.

    Args:
        conn: Open connection.
        season: Current season.
        since: When the run started, in the same clock as ``ingested_at``.
    """
    out = []
    for t in CURRENT_TABLES:
        if t.max_age_days is not None:
            total, old = conn.execute(
                f"SELECT COUNT(*), COUNT(*) FILTER (WHERE ingested_at < ?) "
                f"FROM {t.name} WHERE {t.season_col} = ?",
                [since - timedelta(days=t.max_age_days), season],
            ).fetchone()
            out.append(
                Gate(
                    f"fresh:{t.name}",
                    t.severity,
                    total > 0 and old == 0,
                    f"{old}/{total} {season} rows older than {t.max_age_days} days",
                )
            )
            continue
        total, fresh = conn.execute(
            f"SELECT COUNT(*), COUNT(*) FILTER (WHERE ingested_at >= ?) "
            f"FROM {t.name} WHERE {t.season_col} = ?",
            [since, season],
        ).fetchone()
        share = fresh / total if total else 0.0
        out.append(
            Gate(
                f"fresh:{t.name}",
                t.severity,
                total > 0 and share >= t.min_refreshed,
                f"{fresh}/{total} {season} rows rewritten this run (need {t.min_refreshed:.0%})",
            )
        )
    snapshot = conn.execute(
        "SELECT COUNT(*) FROM bref_contract_players WHERE as_of = ?", [since.date()]
    ).fetchone()[0]
    out.append(
        Gate(
            "fresh:bref_contracts",
            "warn",
            snapshot >= 1000,
            f"{snapshot} players in today's snapshot",
        )
    )
    projected = conn.execute(
        "SELECT COUNT(*) FROM fg_projections WHERE as_of = ?", [since.date()]
    ).fetchone()[0]
    out.append(
        Gate("fresh:fg_projections", "warn", projected >= 4000, f"{projected} projections today")
    )
    return out


def check_domain(conn: duckdb.DuckDBPyConnection, season: int, today: date) -> list[Gate]:
    """Gates on what the data must look like regardless of any earlier run."""
    gates: list[Gate] = []
    clubs, impossible = conn.execute(
        "SELECT COUNT(*), COUNT(*) FILTER (WHERE wins + losses > ? OR wins <= 0) "
        "FROM standings WHERE season = ?",
        [MAX_GAMES, season],
    ).fetchone()
    gates.append(Gate("standings:30 clubs", "fail", clubs == 30, f"{clubs} clubs"))
    gates.append(
        Gate("standings:possible records", "fail", impossible == 0, f"{impossible} impossible rows")
    )

    short = conn.execute(
        "SELECT team_bref, COUNT(*) n FROM team_rosters WHERE season = ? AND ingested_at >= ? "
        "GROUP BY 1 HAVING COUNT(*) < ?",
        [season, datetime.combine(today, datetime.min.time()), MIN_ROSTER],
    ).fetchall()
    rostered = conn.execute(
        "SELECT COUNT(DISTINCT team_bref) FROM team_rosters WHERE season = ? AND ingested_at >= ?",
        [season, datetime.combine(today, datetime.min.time())],
    ).fetchone()[0]
    gates.append(
        Gate(
            "rosters:30 clubs of 25+",
            "fail",
            rostered == 30 and not short,
            f"{rostered} clubs, short: {short}",
        )
    )

    latest = conn.execute("SELECT MAX(date) FROM transactions").fetchone()[0]
    ok = latest is not None and latest >= today - timedelta(days=TRANSACTION_MAX_AGE_DAYS)
    gates.append(Gate("transactions:recent", "fail", ok, f"latest transaction {latest}"))
    return gates


def collect_metrics(conn: duckdb.DuckDBPyConnection, season: int) -> dict[str, Any]:
    """Numbers that must not go backwards between good runs."""
    metrics: dict[str, Any] = {"season": season}
    for t in CURRENT_TABLES:
        metrics[f"rows:{t.name}"] = conn.execute(
            f"SELECT COUNT(*) FROM {t.name} WHERE {t.season_col} = ?", [season]
        ).fetchone()[0]
    war, games = conn.execute(
        "SELECT COALESCE(SUM(war), 0), COALESCE(MAX(g), 0) FROM bwar_batting WHERE year_id = ?",
        [season],
    ).fetchone()
    metrics["bwar_batting_war"] = float(war)
    metrics["bwar_batting_max_g"] = int(games)
    metrics["standings_wins"] = int(
        conn.execute(
            "SELECT COALESCE(SUM(wins), 0) FROM standings WHERE season = ?", [season]
        ).fetchone()[0]
    )
    return metrics


def check_regression(metrics: dict[str, Any], baseline: dict[str, Any] | None) -> list[Gate]:
    """Gates against the last good run. No baseline (first run) or a new season passes."""
    if not baseline or baseline.get("season") != metrics["season"]:
        return [
            Gate("regression", "fail", True, "no baseline for this season; recorded for next run")
        ]
    gates = []
    for key, value in metrics.items():
        if not key.startswith("rows:"):
            continue
        before = baseline.get(key, 0)
        gates.append(
            Gate(
                f"no-shrink:{key[5:]}",
                "fail",
                value >= REGRESSION_FLOOR * before,
                f"{value} rows vs {before}",
            )
        )
    gates.append(
        Gate(
            "bwar:war-only-grows",
            "fail",
            metrics["bwar_batting_war"] >= WAR_FLOOR * baseline["bwar_batting_war"],
            f"{metrics['bwar_batting_war']:.1f} WAR vs {baseline['bwar_batting_war']:.1f}",
        )
    )
    gates.append(
        Gate(
            "bwar:games-only-grow",
            "fail",
            metrics["bwar_batting_max_g"] >= baseline["bwar_batting_max_g"],
            f"{metrics['bwar_batting_max_g']} max G vs {baseline['bwar_batting_max_g']}",
        )
    )
    gates.append(
        Gate(
            "standings:wins-only-grow",
            "fail",
            metrics["standings_wins"] >= baseline["standings_wins"],
            f"{metrics['standings_wins']} wins vs {baseline['standings_wins']}",
        )
    )
    return gates


def run_gates(
    conn: duckdb.DuckDBPyConnection,
    *,
    season: int,
    since: datetime,
    today: date,
    baseline: dict[str, Any] | None,
) -> tuple[list[Gate], dict[str, Any]]:
    """All gates, plus the metrics to store if the run is good."""
    metrics = collect_metrics(conn, season)
    gates = [
        *check_freshness(conn, season, since),
        *check_domain(conn, season, today),
        *check_regression(metrics, baseline),
    ]
    return gates, metrics
