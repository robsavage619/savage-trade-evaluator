"""Compact league-wide player index for similarity / comparable-player search.

One row per active player containing the minimum needed for fingerprint-based
comparison: position, age, latest WAR, salary, plus the latest Statcast
percentile-rank vector. Output is ~150 KB — bundled with the frontend.

Run:
    uv run python scripts/export_player_index.py
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROSTER_PATH = PROJECT_ROOT / "frontend" / "src" / "data" / "seed" / "current_players.json"
OUT_PATH = PROJECT_ROOT / "frontend" / "src" / "data" / "seed" / "player_index.json"

DB_CANDIDATES = [
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


def latest_pitcher_fingerprint(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY year DESC) AS rn
            FROM statcast_pitcher_percentile_ranks
            WHERE player_id IN ({placeholders})
        )
        SELECT player_id, year, xwoba, xera, k_percent, bb_percent, whiff_percent, chase_percent,
               fb_velocity, fb_spin, curve_spin, hard_hit_percent, brl_percent
        FROM ranked WHERE rn = 1
        """,
        ids,
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        out[int(r[0])] = {
            "year": r[1],
            "xwoba": r[2],
            "xera": r[3],
            "k_percent": r[4],
            "bb_percent": r[5],
            "whiff_percent": r[6],
            "chase_percent": r[7],
            "fb_velocity": r[8],
            "fb_spin": r[9],
            "curve_spin": r[10],
            "hard_hit_percent": r[11],
            "brl_percent": r[12],
        }
    return out


def latest_batter_fingerprint(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, dict[str, Any]]:
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY year DESC) AS rn
            FROM statcast_batter_percentile_ranks
            WHERE player_id IN ({placeholders})
        )
        SELECT player_id, year, xwoba, xba, xslg, k_percent, bb_percent, whiff_percent, chase_percent,
               exit_velocity, hard_hit_percent, brl_percent, sprint_speed, bat_speed
        FROM ranked WHERE rn = 1
        """,
        ids,
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        out[int(r[0])] = {
            "year": r[1],
            "xwoba": r[2],
            "xba": r[3],
            "xslg": r[4],
            "k_percent": r[5],
            "bb_percent": r[6],
            "whiff_percent": r[7],
            "chase_percent": r[8],
            "exit_velocity": r[9],
            "hard_hit_percent": r[10],
            "brl_percent": r[11],
            "sprint_speed": r[12],
            "bat_speed": r[13],
        }
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    roster = json.loads(ROSTER_PATH.read_text())
    db = _resolve_db()
    logger.info("opening %s", db)

    all_ids: list[int] = []
    bref_by_id: dict[int, str] = {}
    name_by_id: dict[int, str] = {}
    pos_by_id: dict[int, str | None] = {}
    age_by_id: dict[int, int | None] = {}
    war_by_id: dict[int, float | None] = {}
    salary_by_id: dict[int, int | None] = {}
    hand_pitch: dict[int, str | None] = {}
    hand_bat: dict[int, str | None] = {}
    for t in roster["teams"]:
        for p in t["players"]:
            pid = int(p["mlb_player_id"])
            all_ids.append(pid)
            bref_by_id[pid] = t["bref"]
            name_by_id[pid] = p["name"]
            pos_by_id[pid] = p.get("position_code")
            age_by_id[pid] = p.get("age")
            war_by_id[pid] = p.get("last_war")
            salary_by_id[pid] = p.get("last_salary")
            hand_pitch[pid] = p.get("pitch_hand")
            hand_bat[pid] = p.get("bat_side")

    with duckdb.connect(str(db), read_only=True) as conn:
        pitcher_fp = latest_pitcher_fingerprint(conn, all_ids)
        batter_fp = latest_batter_fingerprint(conn, all_ids)

    out_players: list[dict[str, Any]] = []
    for pid in all_ids:
        is_pitcher = pos_by_id.get(pid) == "1"
        fp = pitcher_fp.get(pid) if is_pitcher else batter_fp.get(pid)
        out_players.append(
            {
                "id": pid,
                "name": name_by_id[pid],
                "team": bref_by_id[pid],
                "pos_code": pos_by_id.get(pid),
                "age": age_by_id.get(pid),
                "war": war_by_id.get(pid),
                "salary": salary_by_id.get(pid),
                "pitch_hand": hand_pitch.get(pid),
                "bat_side": hand_bat.get(pid),
                "is_pitcher": is_pitcher,
                "fp": fp,
            }
        )

    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "count": len(out_players),
        "players": out_players,
    }
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), default=str))
    logger.info("wrote %s — %d players (%.1f KB)", OUT_PATH.relative_to(PROJECT_ROOT), len(out_players), OUT_PATH.stat().st_size / 1024)


if __name__ == "__main__":
    main()
