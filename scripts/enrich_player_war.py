"""Enrich current_players.json with multi-year weighted WAR.

Reads the existing seed file, joins against bwar_batting + bwar_pitching in
DuckDB, and adds three new fields per player:

  war_3yr_wtd      — recency-weighted average WAR over the last 3 *completed*
                     seasons (weights: yr0=0.50, yr-1=0.30, yr-2=0.20).
                     If the most-recent year in the DB is a partial season
                     (max games played across all players < PARTIAL_SEASON_THRESHOLD),
                     it is excluded from the baseline — only full seasons count.

  war_current_pace — annualised WAR pace for the in-progress partial season
                     (last_war × 162 / max_games_in_partial_year).  Null when
                     the current season is complete.

  war_trend        — war_current_pace minus war_3yr_wtd when pace is available,
                     else last_war minus war_3yr_wtd.
                     +ve = currently outperforming baseline (career-year signal).
                     -ve = currently underperforming baseline (slump or small sample).

  war_years        — number of completed seasons included in war_3yr_wtd (1-3).

Writes the enriched file back in-place.  last_war is NOT changed.

Run:
    uv run python scripts/enrich_player_war.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_ROOT / "frontend" / "src" / "data" / "seed" / "current_players.json"

DB_CANDIDATES = [
    Path("/tmp/ste_trades_snapshot.db"),
    PROJECT_ROOT / "data" / "duckdb" / "trades.db",
]

WEIGHTS = {0: 0.50, 1: 0.30, 2: 0.20}  # offset from most-recent *completed* season

# If the latest season's max-g across all players is below this, treat it as
# an in-progress partial year and exclude it from the baseline.
PARTIAL_SEASON_THRESHOLD = 100


def _resolve_db() -> Path:
    for c in DB_CANDIDATES:
        if c.exists():
            return c
    raise FileNotFoundError(f"No DuckDB found in {DB_CANDIDATES}")


def detect_partial_season(conn: duckdb.DuckDBPyConnection) -> tuple[int | None, float | None]:
    """Return (partial_year, max_games) if the latest year is partial, else (None, None)."""
    row = conn.execute("""
        WITH year_max AS (
            SELECT year_id, MAX(g) AS max_g
            FROM (
                SELECT year_id, g FROM bwar_batting
                UNION ALL
                SELECT year_id, g FROM bwar_pitching
            )
            GROUP BY year_id
        )
        SELECT year_id, max_g
        FROM year_max
        ORDER BY year_id DESC
        LIMIT 1
    """).fetchone()
    if row is None:
        return None, None
    year, max_g = int(row[0]), float(row[1]) if row[1] is not None else 0.0
    if max_g < PARTIAL_SEASON_THRESHOLD:
        return year, max_g
    return None, None


def fetch_war_history(
    conn: duckdb.DuckDBPyConnection,
    ids: list[int],
    partial_year: int | None,
    partial_max_g: float | None,
) -> dict[int, dict]:
    """Return per-player multi-year WAR dict keyed by mlb_player_id.

    Args:
        conn: DuckDB connection.
        ids: mlb_player_id list.
        partial_year: Current in-progress season to exclude from baseline.
        partial_max_g: Max games played in partial_year (for pace calc).
    """
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))

    # Exclude partial_year from the baseline query
    year_filter = f"WHERE year_id != {partial_year}" if partial_year else ""

    rows = conn.execute(
        f"""
        WITH seasons AS (
            SELECT mlb_id, year_id, SUM(war) AS war
            FROM (
                SELECT mlb_id, year_id, war FROM bwar_batting  WHERE mlb_id IN ({placeholders})
                UNION ALL
                SELECT mlb_id, year_id, war FROM bwar_pitching WHERE mlb_id IN ({placeholders})
            )
            GROUP BY mlb_id, year_id
        ),
        completed AS (
            SELECT mlb_id, year_id, war FROM seasons {year_filter}
        ),
        latest_completed AS (
            SELECT mlb_id, MAX(year_id) AS last_completed
            FROM completed GROUP BY mlb_id
        ),
        ranked AS (
            SELECT c.mlb_id, c.year_id, c.war,
                   (lc.last_completed - c.year_id) AS yr_offset
            FROM completed c
            JOIN latest_completed lc ON lc.mlb_id = c.mlb_id
            WHERE c.year_id >= lc.last_completed - 2
        )
        SELECT mlb_id, yr_offset, war
        FROM ranked
        ORDER BY mlb_id, yr_offset
        """,
        ids + ids,
    ).fetchall()

    # Partial-year accumulated WAR per player (for pace calc)
    partial_by_id: dict[int, float] = {}
    if partial_year:
        p_rows = conn.execute(
            f"""
            SELECT mlb_id, SUM(war) AS war
            FROM (
                SELECT mlb_id, war FROM bwar_batting
                 WHERE mlb_id IN ({placeholders}) AND year_id = {partial_year}
                UNION ALL
                SELECT mlb_id, war FROM bwar_pitching
                 WHERE mlb_id IN ({placeholders}) AND year_id = {partial_year}
            )
            GROUP BY mlb_id
            """,
            ids + ids,
        ).fetchall()
        partial_by_id = {int(r[0]): float(r[1]) if r[1] is not None else 0.0 for r in p_rows}

    # Group baseline rows by player
    by_id: dict[int, list[tuple[int, float]]] = {}
    for mlb_id, yr_offset, war in rows:
        by_id.setdefault(int(mlb_id), []).append((int(yr_offset), float(war) if war is not None else 0.0))

    pace_factor = (162.0 / partial_max_g) if (partial_year and partial_max_g and partial_max_g > 0) else None

    out: dict[int, dict] = {}
    all_ids_seen = set(by_id.keys()) | set(partial_by_id.keys())
    for mlb_id in all_ids_seen:
        entries = by_id.get(mlb_id, [])
        total_w = sum(WEIGHTS.get(off, 0.0) for off, _ in entries)

        war_3yr_wtd: float | None = None
        if total_w > 0:
            war_3yr_wtd = round(
                sum(WEIGHTS.get(off, 0.0) * war for off, war in entries) / total_w, 3
            )

        war_current_pace: float | None = None
        if partial_year and pace_factor is not None:
            partial_war = partial_by_id.get(mlb_id)
            if partial_war is not None:
                war_current_pace = round(partial_war * pace_factor, 3)

        if war_current_pace is not None and war_3yr_wtd is not None:
            trend = round(war_current_pace - war_3yr_wtd, 3)
        elif war_3yr_wtd is not None:
            last = partial_by_id.get(mlb_id) or next((w for off, w in entries if off == 0), None)
            trend = round(last - war_3yr_wtd, 3) if last is not None else None
        else:
            trend = None

        out[mlb_id] = {
            "war_3yr_wtd": war_3yr_wtd,
            "war_current_pace": war_current_pace,
            "war_trend": trend,
            "war_years": len(entries),
        }
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    logger.info("reading %s", SEED_PATH)
    seed = json.loads(SEED_PATH.read_text())

    all_ids: list[int] = [
        int(p["mlb_player_id"])
        for team in seed["teams"]
        for p in team["players"]
        if p.get("mlb_player_id")
    ]
    logger.info("enriching %d players", len(all_ids))

    db_path = _resolve_db()
    with duckdb.connect(str(db_path), read_only=True) as conn:
        partial_year, partial_max_g = detect_partial_season(conn)
        if partial_year:
            logger.info(
                "partial season detected: %d (max_g=%s) — excluded from baseline, pace_factor=%.2f",
                partial_year,
                partial_max_g,
                162.0 / partial_max_g if partial_max_g else 0,
            )
        history = fetch_war_history(conn, all_ids, partial_year, partial_max_g)

    logger.info("got war history for %d players", len(history))

    enriched = patched = 0
    for team in seed["teams"]:
        for p in team["players"]:
            enriched += 1
            pid = int(p.get("mlb_player_id") or 0)
            h = history.get(pid)
            if h:
                p["war_3yr_wtd"] = h["war_3yr_wtd"]
                p["war_current_pace"] = h["war_current_pace"]
                p["war_trend"] = h["war_trend"]
                p["war_years"] = h["war_years"]
                patched += 1
            else:
                p["war_3yr_wtd"] = None
                p["war_current_pace"] = None
                p["war_trend"] = None
                p["war_years"] = 0

    logger.info("patched %d / %d players", patched, enriched)
    SEED_PATH.write_text(json.dumps(seed, indent=2, default=str))
    logger.info("wrote %s", SEED_PATH)


if __name__ == "__main__":
    main()
