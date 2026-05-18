"""Write one JSON file per active MLB player to ``frontend/public/data/players/``.

The frontend lazy-fetches these on the player profile route, so per-file size
matters more than total bundle size. Each file ~3-15 KB depending on Statcast
coverage. Run after ``refresh_rosters.py``.

Run:
    uv run python scripts/export_player_profiles.py
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
OUT_DIR = PROJECT_ROOT / "frontend" / "public" / "data" / "players"
ROSTER_PATH = PROJECT_ROOT / "frontend" / "src" / "data" / "seed" / "current_players.json"

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


def _rows(conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cursor = conn.execute(sql, params)
    cols = [d[0] for d in cursor.description]
    return [{c: _jsonify(v) for c, v in zip(cols, row, strict=True)} for row in cursor.fetchall()]


def export_player(conn: duckdb.DuckDBPyConnection, pid: int) -> dict[str, Any] | None:
    bio = _rows(
        conn,
        """
        SELECT mlb_player_id, full_name, birth_date, birth_country, height_inches, weight_lbs,
               bat_side, pitch_hand, primary_position_code, primary_position_name, mlb_debut_date,
               last_played_date, active
        FROM mlb_people WHERE mlb_player_id = ?
        """,
        [pid],
    )
    if not bio:
        return None

    career_batting = _rows(
        conn,
        """
        SELECT year_id AS year, team_id, war, salary, g, pa, runs_above_avg, runs_above_avg_off, runs_above_avg_def
        FROM bwar_batting WHERE mlb_id = ? ORDER BY year_id, team_id
        """,
        [pid],
    )

    career_pitching = _rows(
        conn,
        """
        SELECT year_id AS year, team_id, war, salary, g, gs, era_plus, ra, xra, bip
        FROM bwar_pitching WHERE mlb_id = ? ORDER BY year_id, team_id
        """,
        [pid],
    )

    # Statcast percentile ranks (which side based on dominant career)
    is_pitcher = sum(r.get("g") or 0 for r in career_pitching) >= sum(r.get("g") or 0 for r in career_batting)

    pctile_pitcher = _rows(
        conn,
        """
        SELECT year, xwoba, xba, xslg, brl_percent, exit_velocity, hard_hit_percent,
               k_percent, bb_percent, whiff_percent, chase_percent, fb_velocity, fb_spin, curve_spin, xera
        FROM statcast_pitcher_percentile_ranks WHERE player_id = ? ORDER BY year
        """,
        [pid],
    )
    pctile_batter = _rows(
        conn,
        """
        SELECT year, xwoba, xba, xslg, brl_percent, exit_velocity, hard_hit_percent,
               k_percent, bb_percent, whiff_percent, chase_percent, sprint_speed, oaa,
               bat_speed, squared_up_rate, swing_length
        FROM statcast_batter_percentile_ranks WHERE player_id = ? ORDER BY year
        """,
        [pid],
    )

    # Expected stats
    expected_batting = _rows(
        conn,
        """
        SELECT year, pa, ba, est_ba, slg, est_slg, woba, est_woba
        FROM statcast_batting_expected WHERE player_id = ? ORDER BY year
        """,
        [pid],
    )
    expected_pitching = _rows(
        conn,
        """
        SELECT year, pa, ba, est_ba, slg, est_slg, woba, est_woba, era, xera
        FROM statcast_pitching_expected WHERE player_id = ? ORDER BY year
        """,
        [pid],
    )

    # Arsenal (pitcher only — but cheap to query for everyone)
    arsenal = _rows(
        conn,
        """
        SELECT year, pitch_type, pitch_name, pitch_usage, k_percent, whiff_percent, run_value_per_100,
               woba, est_woba, hard_hit_percent
        FROM statcast_pitcher_arsenal_stats WHERE player_id = ? ORDER BY year, pitch_type
        """,
        [pid],
    )

    # Pitch movement (per year+pitch)
    pitch_movement = _rows(
        conn,
        """
        SELECT year, pitch_type, pitch_name, avg_speed, pitch_usage_pct,
               vertical_break_inches, horizontal_break_inches, induced_vertical,
               percentile_diff_vertical, percentile_diff_horizontal
        FROM statcast_pitch_movement WHERE player_id = ? ORDER BY year, pitch_type
        """,
        [pid],
    )

    # Trades — every time this player moved
    trades = _rows(
        conn,
        """
        SELECT u.trade_event_id, u.date AS trade_date, u.from_team_bref, u.to_team_bref,
               u.from_team_name, u.to_team_name
        FROM trade_player_unified u
        WHERE u.mlb_player_id = ?
        ORDER BY u.date
        """,
        [pid],
    )

    # Awards (chronological)
    awards = _rows(
        conn,
        """
        SELECT season, award_name, team_name, votes
        FROM mlb_awards WHERE player_id = ?
        ORDER BY season DESC, award_name
        """,
        [pid],
    )

    # Spotrac contract history
    contracts = _rows(
        conn,
        """
        SELECT season, team_bref, status, service_time, acquired_method,
               base_salary, cap_hit, signing_bonus, position
        FROM spotrac_player_contracts WHERE mlb_player_id = ?
        ORDER BY season DESC
        """,
        [pid],
    )

    return {
        "bio": bio[0],
        "is_pitcher": is_pitcher,
        "career": {
            "batting": career_batting,
            "pitching": career_pitching,
        },
        "percentiles": {
            "pitching": pctile_pitcher,
            "batting": pctile_batter,
        },
        "expected": {
            "batting": expected_batting,
            "pitching": expected_pitching,
        },
        "arsenal": arsenal,
        "pitch_movement": pitch_movement,
        "trades": trades,
        "awards": awards,
        "contracts": contracts,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db_path = _resolve_db()
    roster = json.loads(ROSTER_PATH.read_text())
    ids: list[int] = []
    for team in roster.get("teams", []):
        for p in team.get("players", []):
            pid = p.get("mlb_player_id")
            if pid:
                ids.append(int(pid))
    ids = sorted(set(ids))
    logger.info("exporting %d player profiles to %s", len(ids), OUT_DIR.relative_to(PROJECT_ROOT))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    with duckdb.connect(str(db_path), read_only=True) as conn:
        for pid in ids:
            try:
                payload = export_player(conn, pid)
                if not payload:
                    skipped += 1
                    continue
                # Compact for size
                (OUT_DIR / f"{pid}.json").write_text(json.dumps(payload, separators=(",", ":"), default=_jsonify))
                written += 1
            except Exception as e:
                logger.warning("failed for %s: %s", pid, e)
                skipped += 1

    # Index file
    (OUT_DIR / "_index.json").write_text(
        json.dumps({"generated_at": datetime.utcnow().isoformat(), "count": written, "ids": ids}, default=_jsonify),
    )
    logger.info("wrote %d profiles (%d skipped) — index at _index.json", written, skipped)


if __name__ == "__main__":
    main()
