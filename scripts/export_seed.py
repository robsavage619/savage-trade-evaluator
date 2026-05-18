"""Export seed JSON for the trade-evaluator frontend.

Reads from the live DuckDB and writes typed JSON fixtures into
``frontend/src/data/seed/``. The frontend hydrates from these files in Phase 1;
a FastAPI backend will swap in for the same shapes in Phase 2.

Run:
    uv run python scripts/export_seed.py
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

DB_CANDIDATES = [
    PROJECT_ROOT / "data" / "duckdb" / "trades.db",
    Path(
        "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db"
    ),
]

PRESSLY_TRADE_ID = 371509

NOTABLE_TRADES = [
    371509,  # Pressly -> HOU 2018
    331253,  # Verlander -> HOU 2017
    369676,  # Machado -> LAD 2018
    438093,  # Betts -> LAD 2020
    508180,  # Scherzer + Turner -> LAD 2021
    642337,  # Soto -> SDP 2022
    384506,  # Goldschmidt -> STL 2018
]


def _resolve_db() -> Path:
    for candidate in DB_CANDIDATES:
        if candidate.exists():
            return candidate
    msg = f"No DuckDB file found in any of: {DB_CANDIDATES}"
    raise FileNotFoundError(msg)


def _jsonify(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _rows(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params or [])
    cols = [d[0] for d in cursor.description]
    return [{c: _jsonify(v) for c, v in zip(cols, row, strict=True)} for row in cursor.fetchall()]


def _write(name: str, payload: Any) -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    out = SEED_DIR / f"{name}.json"
    out.write_text(json.dumps(payload, indent=2, default=_jsonify))
    logger.info("wrote %s (%d bytes)", out.relative_to(PROJECT_ROOT), out.stat().st_size)


def export_trade(conn: duckdb.DuckDBPyConnection, trade_id: int) -> dict[str, Any]:
    """Bundle every view we need for a single trade into one JSON object."""
    legs = _rows(conn, "SELECT * FROM trade_player_unified WHERE trade_event_id = ?", [trade_id])
    if not legs:
        msg = f"No legs found for trade_event_id={trade_id}"
        raise ValueError(msg)

    season = int(legs[0]["trade_season"])
    teams = sorted({leg["from_team_bref"] for leg in legs} | {leg["to_team_bref"] for leg in legs})
    player_ids = [leg["mlb_player_id"] for leg in legs if leg["mlb_player_id"] is not None]

    placeholders = ",".join(["?"] * len(teams))
    pid_placeholders = ",".join(["?"] * len(player_ids))

    return {
        "trade_event_id": trade_id,
        "trade_season": season,
        "trade_date": legs[0]["date"],
        "teams": teams,
        "legs": legs,
        "war_window": _rows(
            conn,
            "SELECT * FROM trade_player_war_window WHERE trade_event_id = ?",
            [trade_id],
        ),
        "arsenal_window": _rows(
            conn,
            "SELECT * FROM trade_player_arsenal_window WHERE trade_event_id = ?",
            [trade_id],
        ),
        "pitch_movement_window": _rows(
            conn,
            "SELECT * FROM trade_player_pitch_movement_window WHERE trade_event_id = ?",
            [trade_id],
        ),
        "demographics": _rows(
            conn,
            "SELECT * FROM trade_player_demographics WHERE trade_event_id = ?",
            [trade_id],
        ),
        "naive_baseline": _rows(
            conn,
            "SELECT * FROM naive_baseline_results WHERE trade_event_id = ?",
            [trade_id],
        ),
        "people": _rows(
            conn,
            f"SELECT mlb_player_id, full_name, birth_date, primary_position_name, "
            f"primary_position_code, bat_side, pitch_hand, height_inches, weight_lbs, "
            f"birth_country, mlb_debut_date "
            f"FROM mlb_people WHERE mlb_player_id IN ({pid_placeholders})",
            player_ids,
        ),
        "coaches": _rows(
            conn,
            f"SELECT c.team_id, t.bref_code AS team_bref, c.season, c.job_code, "
            f"c.job_title, c.person_name "
            f"FROM coaches c LEFT JOIN teams t ON t.mlb_team_id = c.team_id "
            f"WHERE c.season = ? AND t.bref_code IN ({placeholders}) "
            f"ORDER BY t.bref_code, c.job_code",
            [season, *teams],
        ),
        "front_office": _rows(
            conn,
            f"SELECT bref_code AS team_bref, role, person_name FROM front_office "
            f"WHERE season = ? AND bref_code IN ({placeholders}) "
            f"ORDER BY bref_code, role",
            [season, *teams],
        ),
        "career_war_pitching": _rows(
            conn,
            f"SELECT mlb_id AS mlb_player_id, year_id AS year, team_id, war, salary "
            f"FROM bwar_pitching WHERE mlb_id IN ({pid_placeholders}) "
            f"ORDER BY mlb_id, year_id, team_id",
            player_ids,
        ),
        "career_war_batting": _rows(
            conn,
            f"SELECT mlb_id AS mlb_player_id, year_id AS year, team_id, war, salary "
            f"FROM bwar_batting WHERE mlb_id IN ({pid_placeholders}) "
            f"ORDER BY mlb_id, year_id, team_id",
            player_ids,
        ),
    }


def export_org_landscape(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """2D org-quality map: dev-credit axis x trade-results axis."""
    # bwar aggregate per team-season for dev signal
    dev = _rows(
        conn,
        """
        WITH all_seasons AS (
            SELECT team_id AS team_bref, year_id AS year, war FROM bwar_batting
            UNION ALL
            SELECT team_id AS team_bref, year_id AS year, war FROM bwar_pitching
        )
        SELECT t.bref_code AS team_bref,
               t.name AS team_name,
               SUM(a.war) FILTER (WHERE a.year BETWEEN 2015 AND 2024) AS dev_war_total,
               AVG(a.war) FILTER (WHERE a.year BETWEEN 2015 AND 2024) AS dev_war_avg
        FROM all_seasons a
        JOIN teams t ON t.bref_code = a.team_bref
        WHERE t.mlb_team_id BETWEEN 100 AND 199
        GROUP BY t.bref_code, t.name
        ORDER BY t.bref_code
        """,
    )

    # trade results: mean surplus per receiving team from naive baseline (3yr window)
    trade_results = _rows(
        conn,
        """
        SELECT team_bref,
               AVG(surplus) AS mean_surplus_3yr,
               COUNT(*) AS n_trades
        FROM naive_baseline_results
        WHERE outcome_window_years = 3
        GROUP BY team_bref
        ORDER BY team_bref
        """,
    )

    return {"dev": dev, "trade_results": trade_results}


def export_gm_regimes(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Per-decision-maker trade summary stats. Showcase: Daniels' -2.54 WAR sell-high."""
    return _rows(
        conn,
        """
        WITH decision_maker AS (
            SELECT DISTINCT bref_code AS team_bref, season,
                   COALESCE(
                       MAX(person_name) FILTER (WHERE role = 'President'),
                       MAX(person_name) FILTER (WHERE role = 'General Manager')
                   ) AS gm_name
            FROM front_office
            GROUP BY bref_code, season
        ),
        trades_with_gm AS (
            SELECT n.team_bref,
                   n.trade_season,
                   d.gm_name,
                   n.surplus,
                   n.war_received,
                   n.war_given_up
            FROM naive_baseline_results n
            JOIN decision_maker d
              ON d.team_bref = n.team_bref AND d.season = n.trade_season
            WHERE n.outcome_window_years = 3 AND d.gm_name IS NOT NULL
        )
        SELECT gm_name,
               team_bref,
               COUNT(*) AS n_trades,
               AVG(surplus) AS mean_surplus,
               AVG(war_received) AS mean_war_received,
               AVG(war_given_up) AS mean_war_given_up,
               MIN(trade_season) AS first_season,
               MAX(trade_season) AS last_season
        FROM trades_with_gm
        GROUP BY gm_name, team_bref
        HAVING n_trades >= 3
        ORDER BY mean_surplus
        """,
    )


def export_kpct_finding(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Pre-trade K%-trajectory vs T+1 K% delta scatter for the confirmed finding."""
    return _rows(
        conn,
        """
        SELECT trade_event_id,
               mlb_player_id,
               player_name,
               from_team_bref,
               to_team_bref,
               trade_season,
               k_percent_t_minus_1,
               k_percent_t_plus_1,
               (k_percent_t_plus_1 - k_percent_t_minus_1) AS k_delta
        FROM trade_player_arsenal_window
        WHERE k_percent_t_minus_1 IS NOT NULL
          AND k_percent_t_plus_1 IS NOT NULL
        """,
    )


def export_trade_index(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Searchable index of notable trades for the trade explorer."""
    return _rows(
        conn,
        """
        WITH player_war AS (
            SELECT trade_event_id, SUM(ABS(COALESCE(war_t_plus_1, 0))) AS total_war_flow
            FROM trade_player_war_window
            GROUP BY trade_event_id
        )
        SELECT e.trade_event_id,
               e.date AS trade_date,
               e.season AS trade_season,
               e.player_count,
               e.description,
               COALESCE(pw.total_war_flow, 0) AS total_war_flow
        FROM trade_events e
        LEFT JOIN player_war pw ON pw.trade_event_id = e.trade_event_id
        WHERE e.season BETWEEN 2010 AND 2024
        ORDER BY total_war_flow DESC NULLS LAST
        LIMIT 100
        """,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db_path = _resolve_db()
    logger.info("opening %s", db_path)
    with duckdb.connect(str(db_path), read_only=True) as conn:
        for tid in NOTABLE_TRADES:
            payload = export_trade(conn, tid)
            _write(f"trade_{tid}", payload)
        _write("org_landscape", export_org_landscape(conn))
        _write("gm_regimes", export_gm_regimes(conn))
        _write("kpct_finding", export_kpct_finding(conn))
        try:
            _write("trade_index", export_trade_index(conn))
        except duckdb.Error as e:
            logger.warning("trade_index export skipped: %s", e)


if __name__ == "__main__":
    main()
