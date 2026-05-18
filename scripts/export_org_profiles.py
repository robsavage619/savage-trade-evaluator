"""Export a per-team scouting profile bundle for every MLB org.

Writes ``frontend/src/data/seed/org_profiles.json`` — one comprehensive bundle
keyed by bref containing trajectory, payroll, dev signature, trade DNA, FO
continuity, and roster-aggregate context. Feeds the deep ``/orgs/:bref``
profile route.

Run:
    uv run python scripts/export_org_profiles.py
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = PROJECT_ROOT / "frontend" / "src" / "data" / "seed"
OUT_PATH = SEED_DIR / "org_profiles.json"

DB_CANDIDATES = [
    Path("/tmp/ste_trades_snapshot.db"),
    PROJECT_ROOT / "data" / "duckdb" / "trades.db",
    Path(
        "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db"
    ),
]


def _resolve_db() -> Path:
    for c in DB_CANDIDATES:
        if c.exists():
            return c
    msg = f"No DuckDB found in {DB_CANDIDATES}"
    raise FileNotFoundError(msg)


def _jsonify(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _rows(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    cols = [d[0] for d in cursor.description]
    return [{c: _jsonify(v) for c, v in zip(cols, row, strict=True)} for row in cursor.fetchall()]


def export_for_team(conn: duckdb.DuckDBPyConnection, bref: str) -> dict[str, Any]:
    # 1) Trajectory — last 10 seasons of records, run diff, team WAR
    trajectory = _rows(
        conn,
        """
        WITH s AS (
            SELECT season, wins, losses, win_pct FROM standings WHERE bref_code = ?
        ),
        bw AS (
            SELECT year_id AS season, SUM(war) AS war_total
            FROM (
                SELECT year_id, war FROM bwar_batting WHERE team_id = ?
                UNION ALL
                SELECT year_id, war FROM bwar_pitching WHERE team_id = ?
            ) AS u
            GROUP BY year_id
        ),
        team_stats AS (
            SELECT season, MAX(CASE WHEN stat_group='hitting' THEN runs END) AS runs_scored,
                   MAX(CASE WHEN stat_group='pitching' THEN earned_runs END) AS runs_allowed
            FROM team_season_stats
            WHERE team_bref = ? OR team_id IN (SELECT mlb_team_id FROM teams WHERE bref_code = ?)
            GROUP BY season
        )
        SELECT s.season, s.wins, s.losses, s.win_pct,
               bw.war_total,
               ts.runs_scored, ts.runs_allowed
        FROM s
        LEFT JOIN bw ON bw.season = s.season
        LEFT JOIN team_stats ts ON ts.season = s.season
        WHERE s.season BETWEEN 2015 AND 2025
        ORDER BY s.season
        """,
        [bref, bref, bref, bref, bref],
    )

    # 2) Dev signature — most-recent rows from team_season_features
    dev_rows = _rows(
        conn,
        """
        SELECT season, prior_year_war, org_pitcher_k_jump_3yr, org_hitter_xwoba_jump_3yr,
               org_dev_fit_pitching, org_dev_fit_hitting, farm_war_top_10
        FROM team_season_features
        WHERE bref_code = ? AND season BETWEEN 2015 AND 2026
        ORDER BY season DESC
        """,
        [bref],
    )

    # Aggregate dev signature: average over last 5 seasons
    recent = [r for r in dev_rows if r["org_pitcher_k_jump_3yr"] is not None][:5]
    avg_k_jump = sum(r["org_pitcher_k_jump_3yr"] for r in recent) / max(1, len(recent)) if recent else None
    recent_x = [r for r in dev_rows if r["org_hitter_xwoba_jump_3yr"] is not None][:5]
    avg_x_jump = sum(r["org_hitter_xwoba_jump_3yr"] for r in recent_x) / max(1, len(recent_x)) if recent_x else None

    # 3) Trade DNA — last 10 trades from naive_baseline_results
    trade_dna = _rows(
        conn,
        """
        SELECT n.trade_event_id, n.trade_season, n.players_received, n.players_given_up,
               n.war_received, n.war_given_up, n.surplus,
               e.description
        FROM naive_baseline_results n
        JOIN trade_events e ON e.trade_event_id = n.trade_event_id
        WHERE n.team_bref = ? AND n.outcome_window_years = 3
        ORDER BY n.trade_season DESC, ABS(n.surplus) DESC
        LIMIT 12
        """,
        [bref],
    )

    # Trade aggregate stats
    trade_summary = _rows(
        conn,
        """
        SELECT COUNT(*) AS n_trades,
               AVG(surplus) AS mean_surplus,
               AVG(war_received) AS mean_received,
               AVG(war_given_up) AS mean_given,
               SUM(CASE WHEN surplus > 0 THEN 1 ELSE 0 END) AS n_positive,
               MIN(surplus) AS min_surplus,
               MAX(surplus) AS max_surplus
        FROM naive_baseline_results
        WHERE team_bref = ? AND outcome_window_years = 3
        """,
        [bref],
    )

    # 4) FO continuity — last 12 seasons
    fo_history = _rows(
        conn,
        """
        SELECT season, role, person_name
        FROM front_office
        WHERE bref_code = ? AND role IN ('President','General Manager','Manager','Farm Director','Scouting Director')
          AND season BETWEEN 2015 AND 2026
        ORDER BY season DESC, role
        """,
        [bref],
    )

    # 5) Coaches — current snapshot (latest available season)
    latest_coach_season_rows = conn.execute(
        """
        SELECT MAX(season) FROM coaches
         WHERE team_id IN (SELECT mlb_team_id FROM teams WHERE bref_code = ?)
        """,
        [bref],
    ).fetchone()
    latest_coach_season = latest_coach_season_rows[0] if latest_coach_season_rows else None
    coaches = []
    if latest_coach_season:
        coaches = _rows(
            conn,
            """
            SELECT c.season, c.job_code, c.job_title, c.person_name
            FROM coaches c
            JOIN teams t ON t.mlb_team_id = c.team_id
            WHERE t.bref_code = ? AND c.season = ?
            ORDER BY c.job_code
            """,
            [bref, latest_coach_season],
        )

    # 6) Roster aggregate context — most recent season's bwar
    latest_war_season_rows = conn.execute(
        """
        SELECT MAX(year_id) FROM (
            SELECT year_id FROM bwar_batting WHERE team_id = ?
            UNION ALL
            SELECT year_id FROM bwar_pitching WHERE team_id = ?
        )
        """,
        [bref, bref],
    ).fetchone()
    latest_war_season = latest_war_season_rows[0] if latest_war_season_rows else None

    payroll_top = []
    age_curve = []
    if latest_war_season:
        payroll_top = _rows(
            conn,
            """
            WITH season_war AS (
                SELECT mlb_id, name_common, year_id, team_id, war, salary, 'P' AS role
                FROM bwar_pitching WHERE team_id = ? AND year_id = ?
                UNION ALL
                SELECT mlb_id, name_common, year_id, team_id, war, salary, 'B' AS role
                FROM bwar_batting WHERE team_id = ? AND year_id = ?
            )
            SELECT mlb_id, name_common, role, war, salary
            FROM season_war
            WHERE salary IS NOT NULL
            ORDER BY salary DESC
            LIMIT 12
            """,
            [bref, latest_war_season, bref, latest_war_season],
        )

        # Age curve (avg age weighted by WAR)
        age_curve_rows = _rows(
            conn,
            """
            WITH season_war AS (
                SELECT mlb_id, year_id, war, 'P' AS role
                FROM bwar_pitching WHERE team_id = ? AND year_id = ?
                UNION ALL
                SELECT mlb_id, year_id, war, 'B' AS role
                FROM bwar_batting WHERE team_id = ? AND year_id = ?
            )
            SELECT sw.mlb_id, m.full_name, m.birth_date, sw.war, sw.role, m.primary_position_code AS position_code,
                   CAST(sw.year_id - EXTRACT(YEAR FROM m.birth_date) AS INTEGER) AS age
            FROM season_war sw
            JOIN mlb_people m ON m.mlb_player_id = sw.mlb_id
            WHERE m.birth_date IS NOT NULL AND sw.war IS NOT NULL
            """,
            [bref, latest_war_season, bref, latest_war_season],
        )
        age_curve = age_curve_rows

    # 7) Org placement on dev/trade 2D map (recompute aggregate)
    placement = _rows(
        conn,
        """
        WITH dev AS (
            SELECT SUM(war) AS dev_war
            FROM (
                SELECT war FROM bwar_batting WHERE team_id = ? AND year_id BETWEEN 2015 AND 2024
                UNION ALL
                SELECT war FROM bwar_pitching WHERE team_id = ? AND year_id BETWEEN 2015 AND 2024
            )
        ),
        trade AS (
            SELECT AVG(surplus) AS mean_surplus, COUNT(*) AS n_trades
            FROM naive_baseline_results WHERE team_bref = ? AND outcome_window_years = 3
        )
        SELECT dev.dev_war, trade.mean_surplus, trade.n_trades
        FROM dev, trade
        """,
        [bref, bref, bref],
    )

    # Spotrac team payroll history
    spotrac_payroll = _rows(
        conn,
        """
        SELECT season, active_players, active_payroll, dead_money, injured_payroll, total_payroll
        FROM spotrac_team_payroll WHERE team_bref = ? AND season BETWEEN 2018 AND 2026
        ORDER BY season DESC
        """,
        [bref],
    )

    # Spotrac contracts breakdown by status (current/latest season)
    contract_breakdown = _rows(
        conn,
        """
        WITH latest AS (
            SELECT MAX(season) AS s FROM spotrac_player_contracts WHERE team_bref = ?
        )
        SELECT s.status, COUNT(*) AS n, SUM(s.cap_hit) AS total_cap, AVG(s.service_time) AS avg_svc
        FROM spotrac_player_contracts s, latest l
        WHERE s.team_bref = ? AND s.season = l.s AND s.status IS NOT NULL AND s.status <> ''
        GROUP BY s.status
        ORDER BY total_cap DESC NULLS LAST
        """,
        [bref, bref],
    )

    return {
        "bref": bref,
        "trajectory": trajectory,
        "dev_signature": {
            "avg_pitcher_k_jump_3yr": avg_k_jump,
            "avg_hitter_xwoba_jump_3yr": avg_x_jump,
            "history": dev_rows,
        },
        "spotrac_payroll": spotrac_payroll,
        "contract_breakdown": contract_breakdown,
        "trade_dna": {
            "recent": trade_dna,
            "summary": trade_summary[0] if trade_summary else None,
        },
        "fo_history": fo_history,
        "coaches": coaches,
        "coach_season": latest_coach_season,
        "payroll": {
            "season": latest_war_season,
            "top_contracts": payroll_top,
        },
        "age_curve": age_curve,
        "org_placement": placement[0] if placement else None,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db_path = _resolve_db()
    logger.info("opening %s", db_path)

    out: dict[str, Any] = {"generated_at": datetime.utcnow().isoformat(), "teams": {}}
    with duckdb.connect(str(db_path), read_only=True) as conn:
        bref_rows = conn.execute(
            "SELECT bref_code FROM teams WHERE mlb_team_id BETWEEN 100 AND 199 ORDER BY bref_code"
        ).fetchall()
        for (bref,) in bref_rows:
            logger.info("profiling %s…", bref)
            out["teams"][bref] = export_for_team(conn, bref)

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=_jsonify))
    logger.info("wrote %s — %d teams", OUT_PATH.relative_to(PROJECT_ROOT), len(out["teams"]))


if __name__ == "__main__":
    main()
