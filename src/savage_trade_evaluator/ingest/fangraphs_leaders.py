"""Ingest FanGraphs batting/pitching leaderboards via the Firecrawl stealth proxy.

FanGraphs leaderboards are Cloudflare-gated — pybaseball / curl_cffi / cloudscraper
all 403 (see catalog). The Firecrawl stealth proxy solves the challenge and returns
the underlying JSON API response cleanly.

The leaderboard data API:
    https://www.fangraphs.com/api/leaders/major-league/data
        ?pos=all&stats={bat|pit}&lg=all&qual=0&season={Y}&season1={Y}
        &month=0&team=0&pageitems=10000&pagenum=1&ind=0&type=8&...

``type=8`` returns the full stat bundle (475 batting / 544 pitching columns). We
keep a curated, model-relevant subset (park-adjusted rates, component WAR, batted
ball, plate discipline) keyed on (season, fg_playerid). ``xMLBAMID`` is stored as
``mlbam_id`` for direct bridging to the rest of the warehouse.

Auth: reads ``FIRECRAWL_API_KEY`` from the environment and calls
``api.firecrawl.dev/v1/scrape`` directly (no MCP dependency).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pandas as pd

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "fangraphs"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
FG_DATA_URL = "https://www.fangraphs.com/api/leaders/major-league/data"
RATE_LIMIT_SECONDS = 2.0
SCRAPE_TIMEOUT = 120

# Cache of raw Firecrawl responses (one file per stats-type/season), so the
# leaderboards can be ingested without a Firecrawl REST key — fetch via the
# Firecrawl MCP, drop the response here as {stats}_{season}.json, then ingest.
DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "fangraphs_cache"

# FG JSON field -> our column name. Defensive: missing fields become NULL.
_BAT_FIELD_MAP: dict[str, str] = {
    "playerid": "fg_playerid",
    "xMLBAMID": "mlbam_id",
    "PlayerName": "player_name",
    "Team": "team",
    "position": "position",
    "Age": "age",
    "G": "g",
    "PA": "pa",
    "AB": "ab",
    "AVG": "avg",
    "OBP": "obp",
    "SLG": "slg",
    "OPS": "ops",
    "ISO": "iso",
    "BABIP": "babip",
    "wOBA": "woba",
    "wRC+": "wrc_plus",
    "WAR": "war",
    "WAROld": "war_old",
    "wRAA": "wraa",
    "BB%": "bb_pct",
    "K%": "k_pct",
    "Batting": "batting",
    "Fielding": "fielding",
    "BaseRunning": "base_running",
    "Positional": "pos_adj",
    "Replacement": "replacement",
    "Defense": "defense",
    "Offense": "offense",
    "RAR": "rar",
    "Dollars": "dollars",
    "Spd": "spd",
    "wBsR": "wbsr",
    "GB%": "gb_pct",
    "FB%": "fb_pct",
    "LD%": "ld_pct",
    "HR/FB": "hr_fb",
    "Soft%": "soft_pct",
    "Med%": "med_pct",
    "Hard%": "hard_pct",
    "Pull%": "pull_pct",
    "Cent%": "cent_pct",
    "Oppo%": "oppo_pct",
    "O-Swing%": "o_swing_pct",
    "Z-Swing%": "z_swing_pct",
    "Swing%": "swing_pct",
    "Contact%": "contact_pct",
    "SwStr%": "swstr_pct",
    "Zone%": "zone_pct",
    "F-Strike%": "f_strike_pct",
}

_PIT_FIELD_MAP: dict[str, str] = {
    "playerid": "fg_playerid",
    "xMLBAMID": "mlbam_id",
    "PlayerName": "player_name",
    "Team": "team",
    "Age": "age",
    "W": "w",
    "L": "l",
    "G": "g",
    "GS": "gs",
    "IP": "ip",
    "TBF": "tbf",
    "ERA": "era",
    "FIP": "fip",
    "xFIP": "xfip",
    "SIERA": "siera",
    "WHIP": "whip",
    "WAR": "war",
    "RAR": "rar",
    "Dollars": "dollars",
    "K/9": "k_9",
    "BB/9": "bb_9",
    "HR/9": "hr_9",
    "K%": "k_pct",
    "BB%": "bb_pct",
    "K-BB%": "k_bb_pct",
    "LOB%": "lob_pct",
    "BABIP": "babip",
    "GB%": "gb_pct",
    "FB%": "fb_pct",
    "LD%": "ld_pct",
    "HR/FB": "hr_fb",
    "Soft%": "soft_pct",
    "Hard%": "hard_pct",
    "O-Swing%": "o_swing_pct",
    "SwStr%": "swstr_pct",
    "Zone%": "zone_pct",
    "F-Strike%": "f_strike_pct",
    "Contact%": "contact_pct",
    "FBv": "fbv",
}

_INT_COLS = frozenset({"mlbam_id", "g", "pa", "ab", "w", "l", "gs", "tbf"})


def _firecrawl_scrape(url: str, api_key: str) -> str:
    """POST to Firecrawl /v1/scrape with stealth proxy; return the raw body string."""
    resp = httpx.post(
        FIRECRAWL_SCRAPE_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"url": url, "formats": ["rawHtml"], "proxy": "stealth", "waitFor": 5000},
        timeout=SCRAPE_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success", False):
        raise RuntimeError(f"Firecrawl scrape failed: {payload.get('error', payload)}")
    raw = payload.get("data", {}).get("rawHtml")
    if not raw:
        raise RuntimeError("Firecrawl response missing data.rawHtml")
    return raw


def _fg_url(stats: str, season: int) -> str:
    return (
        f"{FG_DATA_URL}?pos=all&stats={stats}&lg=all&qual=0"
        f"&season={season}&season1={season}&month=0&team=0"
        f"&pageitems=10000&pagenum=1&ind=0&type=8&sortstat=WAR&sortdir=desc"
    )


def _coerce(col: str, val: Any) -> Any:
    if val is None or val == "":
        return None
    if col in _INT_COLS:
        try:
            return round(float(val))
        except (ValueError, TypeError):
            return None
    if col in ("fg_playerid", "player_name", "team", "position"):
        return str(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _extract_inner(text: str) -> dict[str, Any]:
    """Return the FG leaderboard payload ({"data": [...]}) from raw text.

    Handles three shapes:
      1. the bare FG JSON string ({"data": [...], "totalCount": N})
      2. a Firecrawl MCP/REST wrapper ({"rawHtml": "<json string>", ...})
      3. a Firecrawl REST envelope ({"success": true, "data": {"rawHtml": ...}})
    """
    obj = json.loads(text)
    if isinstance(obj, dict) and "success" in obj and "data" in obj:
        obj = obj["data"]
    if isinstance(obj, dict) and "rawHtml" in obj:
        obj = json.loads(obj["rawHtml"])
    if not isinstance(obj, dict) or "data" not in obj:
        raise ValueError("could not locate FG leaderboard 'data' array in payload")
    return obj


def _rows_from_payload(raw: str, field_map: dict[str, str], season: int) -> list[dict[str, Any]]:
    inner = _extract_inner(raw)
    out = []
    for rec in inner.get("data", []):
        row: dict[str, Any] = {"season": season}
        for fg_field, col in field_map.items():
            row[col] = _coerce(col, rec.get(fg_field))
        if row.get("fg_playerid") is None:
            continue
        out.append(row)
    return out


def _ingest_raw(stats: str, season: int, raw: str) -> int:
    """Parse a raw FG leaderboard payload and upsert into the matching table."""
    field_map = _BAT_FIELD_MAP if stats == "bat" else _PIT_FIELD_MAP
    table = "fangraphs_batting_leaders" if stats == "bat" else "fangraphs_pitching_leaders"
    rows = _rows_from_payload(raw, field_map, season)
    with db.connect() as conn:
        n = _upsert(conn, table, rows)
    logger.info("ingested %d %s rows for %d", n, stats, season)
    return n


def _upsert(conn: duckdb.DuckDBPyConnection, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows)
    cols = ", ".join(df.columns)
    staging = f"_staging_{table}"
    conn.register(staging, df)
    try:
        conn.execute(
            f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {staging} "
            f"ON CONFLICT (season, fg_playerid) DO NOTHING"
        )
    finally:
        conn.unregister(staging)
    return len(rows)


def ingest_year(stats: str, season: int, api_key: str | None = None) -> int:
    """Fetch one (stats, season) leaderboard and insert into the matching table.

    Args:
        stats: "bat" or "pit".
        season: Season year.
        api_key: Firecrawl key; falls back to ``FIRECRAWL_API_KEY`` env var.

    Returns:
        Number of rows inserted.
    """
    if stats not in ("bat", "pit"):
        raise ValueError(f"stats must be 'bat' or 'pit', got {stats!r}")
    key = api_key or os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY not set in environment")

    raw = _firecrawl_scrape(_fg_url(stats, season), key)
    return _ingest_raw(stats, season, raw)


def fg_url(stats: str, season: int) -> str:
    """Public accessor for the FG data URL (e.g. to fetch via the Firecrawl MCP)."""
    if stats not in ("bat", "pit"):
        raise ValueError(f"stats must be 'bat' or 'pit', got {stats!r}")
    return _fg_url(stats, season)


def ingest_from_cache(stats: str, season: int, cache_dir: Path | None = None) -> int:
    """Ingest one (stats, season) from a cached Firecrawl response file.

    Reads ``{cache_dir}/{stats}_{season}.json`` (raw Firecrawl response or bare
    FG JSON) and upserts. This is the no-REST-key path: fetch via the Firecrawl
    MCP, save the response here, then ingest.
    """
    if stats not in ("bat", "pit"):
        raise ValueError(f"stats must be 'bat' or 'pit', got {stats!r}")
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    path = cache_dir / f"{stats}_{season}.json"
    if not path.exists():
        logger.warning("FG cache missing: %s", path)
        return 0
    return _ingest_raw(stats, season, path.read_text())


def ingest_range_from_cache(
    stats_types: tuple[str, ...] = ("bat", "pit"),
    start: int = 2010,
    end: int = 2024,
    cache_dir: Path | None = None,
) -> dict[str, int]:
    """Ingest all cached (stats_type, season) files in a range."""
    results: dict[str, int] = {}
    total = 0
    for stats in stats_types:
        for season in range(start, end + 1):
            n = ingest_from_cache(stats, season, cache_dir=cache_dir)
            results[f"{stats}-{season}"] = n
            total += n
    results["TOTAL"] = total
    return results


def ingest_range(
    stats_types: tuple[str, ...] = ("bat", "pit"),
    start: int = 2010,
    end: int = 2024,
) -> dict[str, int]:
    """Fetch all (stats_type, season) combinations in a range.

    Returns a dict of {"{stats}-{season}": rows} plus a "TOTAL" key.
    """
    key = os.environ.get("FIRECRAWL_API_KEY")
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY not set in environment")

    results: dict[str, int] = {}
    total = 0
    for stats in stats_types:
        for season in range(start, end + 1):
            n = ingest_year(stats, season, api_key=key)
            results[f"{stats}-{season}"] = n
            total += n
            time.sleep(RATE_LIMIT_SECONDS)
    results["TOTAL"] = total
    return results
