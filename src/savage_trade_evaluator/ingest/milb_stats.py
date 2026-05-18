"""Ingest MiLB seasonal stats from the MLB Stats API.

Pulls per-player seasonal hitting + pitching stats at AAA / AA / High-A /
Single-A levels. Same endpoint as MLB stats — only the ``sportId`` param
changes:

  sportId=11  Triple-A
  sportId=12  Double-A
  sportId=13  High-A
  sportId=14  Single-A

The response shape is identical to MLB stats — same player.id (MLBAM),
same stat keys per group ('hitting' / 'pitching'). Pagination is
limit+offset; totalSplits is in the response root.

One row per (player, season, sport_id, team_id, group). Same player can
appear at multiple levels in one season (promotions / demotions).
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd

from savage_trade_evaluator.config import MLB_STATS_API_BASE
from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "mlb-stats-api"
HTTP_TIMEOUT_SECONDS = 60.0
PAGE_SIZE = 500
RATE_LIMIT_SECONDS = 0.5

MILB_SPORT_IDS: tuple[int, ...] = (11, 12, 13, 14)
GROUPS: tuple[str, ...] = ("hitting", "pitching")


def _to_float(raw: Any) -> float | None:
    """Convert API stat values that may be strings like '.250' or '-.--' to float."""
    if raw is None:
        return None
    if isinstance(raw, int | float):
        return float(raw)
    s = str(raw).strip()
    if not s or s.startswith(("-", ".-")) and not s.lstrip("-").replace(".", "").isdigit():
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(float(str(raw)))
    except (ValueError, TypeError):
        return None


def fetch_page(
    season: int,
    sport_id: int,
    group: str,
    offset: int,
    client: httpx.Client | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Pull one page of MiLB seasonal stats.

    Returns (splits, total_splits). Caller paginates until offset >= total.
    """
    params = {
        "stats": "season",
        "group": group,
        "season": season,
        "sportId": sport_id,
        "playerPool": "All",
        "limit": PAGE_SIZE,
        "offset": offset,
    }
    owns = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        r = client.get(f"{MLB_STATS_API_BASE}/stats", params=params)
        r.raise_for_status()
        payload = r.json()
    finally:
        if owns:
            client.close()

    stat_group = payload.get("stats", [{}])[0]
    splits = stat_group.get("splits", []) or []
    total = int(stat_group.get("totalSplits", len(splits)) or 0)
    return splits, total


def _normalize(
    raw: dict[str, Any], season: int, sport_id: int, group: str
) -> dict[str, Any] | None:
    """Convert one MLB-Stats-API split to our DuckDB row shape."""
    player = raw.get("player") or {}
    team = raw.get("team") or {}
    league = raw.get("league") or {}
    position = raw.get("position") or {}
    stat = raw.get("stat") or {}
    pid = _to_int(player.get("id"))
    tid = _to_int(team.get("id"))
    if pid is None or tid is None:
        return None
    return {
        "mlb_player_id": pid,
        "season": season,
        "sport_id": sport_id,
        "team_id": tid,
        "group_name": group,
        "player_name": player.get("fullName"),
        "team_name": team.get("name"),
        "league_id": _to_int(league.get("id")),
        "position": position.get("abbreviation") or position.get("code"),
        "age": _to_int(stat.get("age")),
        "games_played": _to_int(stat.get("gamesPlayed")),
        "plate_appearances": _to_int(stat.get("plateAppearances")),
        "at_bats": _to_int(stat.get("atBats")),
        "runs": _to_int(stat.get("runs")),
        "hits": _to_int(stat.get("hits")),
        "doubles": _to_int(stat.get("doubles")),
        "triples": _to_int(stat.get("triples")),
        "home_runs": _to_int(stat.get("homeRuns")),
        "rbi": _to_int(stat.get("rbi")),
        "stolen_bases": _to_int(stat.get("stolenBases")),
        "strikeouts": _to_int(stat.get("strikeOuts")),
        "walks": _to_int(stat.get("baseOnBalls")),
        "hbp": _to_int(stat.get("hitByPitch")),
        "avg": _to_float(stat.get("avg")),
        "obp": _to_float(stat.get("obp")),
        "slg": _to_float(stat.get("slg")),
        "ops": _to_float(stat.get("ops")),
        "babip": _to_float(stat.get("babip")),
        "innings_pitched": _to_float(stat.get("inningsPitched")),
        "era": _to_float(stat.get("era")),
        "wins": _to_int(stat.get("wins")),
        "losses": _to_int(stat.get("losses")),
        "saves": _to_int(stat.get("saves")),
        "games_started": _to_int(stat.get("gamesStarted")),
        "source": SOURCE,
    }


def _upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = list(rows[0].keys())
    df = pd.DataFrame(rows, columns=columns)
    conn.register("_staging_milb", df)
    try:
        conn.execute(
            f"INSERT INTO milb_player_seasons ({', '.join(columns)}) "
            f"SELECT {', '.join(columns)} FROM _staging_milb "
            "ON CONFLICT (mlb_player_id, season, sport_id, team_id, group_name) "
            "DO NOTHING"
        )
    finally:
        conn.unregister("_staging_milb")
    return len(rows)


def ingest_season(
    season: int,
    sport_ids: tuple[int, ...] = MILB_SPORT_IDS,
    groups: tuple[str, ...] = GROUPS,
) -> int:
    """Fetch and store one MiLB season across the requested levels + groups."""
    total_written = 0
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client, db.connect() as conn:
        schemas.initialize(conn)
        for sport_id in sport_ids:
            for group in groups:
                offset = 0
                total_remote = None
                while True:
                    splits, total = fetch_page(season, sport_id, group, offset, client=client)
                    if total_remote is None:
                        total_remote = total
                    if not splits:
                        break
                    rows = [
                        r
                        for r in (_normalize(s, season, sport_id, group) for s in splits)
                        if r is not None
                    ]
                    total_written += _upsert(conn, rows)
                    offset += len(splits)
                    time.sleep(RATE_LIMIT_SECONDS)
                    if offset >= (total_remote or 0):
                        break
                logger.info(
                    "milb %s sport=%d season=%d: %d rows (total=%d)",
                    group, sport_id, season, offset, total_remote or 0,
                )
    return total_written


def ingest_range(start: int, end: int) -> int:
    """Ingest MiLB stats for every season in [start, end] inclusive."""
    grand = 0
    for s in range(start, end + 1):
        grand += ingest_season(s)
    return grand
