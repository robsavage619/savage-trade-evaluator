"""Ingest MLB Pipeline top-100 prospect rankings.

MLB.com (mlb.com/milb/prospects/<year>) publishes an annual top-100 prospect list.
The data is server-rendered HTML in a clean `<table>` structure. Each row has
the rank, the player's name and MLB Stats API player_id (extractable from the
headshot URL), team_id (extractable from the team-logo URL), position, current
level, and age.

**Notable absence:** MLB Pipeline does **not** publish FV grades. Only the rank.
This is a coarse proxy — top-10 ranks roughly correspond to 55+ FV per industry
norms; top-50 to ~50 FV; 50-100 to 45-50 FV. The rank itself is the feature.

FanGraphs prospect grades (which include FV + variance + tool grades) are
Cloudflare-blocked. MLB Pipeline is the cleanest publicly-scrapeable substitute.

Coverage probe confirmed pages 200 OK for 2018-2025.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.storage import db, schemas, teams

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "mlb-pipeline"
HTTP_TIMEOUT_SECONDS = 30.0
RATE_LIMIT_SECONDS = 2.0  # MLB.com is fast but polite

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}


# Each <tr> in the rankings table follows the pattern:
#   <tr><td>RANK</td><td>...<a href="...stories/PLAYER-SLUG-PLAYER_ID">...</a>
#       <div>NAME</div></td><td>POSITION</td>
#       <td>...team-cap-on-light/TEAM_ID.svg...<div>TEAM_NAME</div></td>
#       <td>...<div>LEVEL</div>...</td><td>AGE</td><td>BATS</td><td>...</td></tr>
ROW_PATTERN = re.compile(
    r"<tr[^>]*>\s*"
    r"<td[^>]*>(\d+)</td>\s*"  # rank
    r"<td[^>]*>.*?href=\"[^\"]*?/people/(\d+)/headshot[^\"]*\""  # player_id from headshot URL
    r".*?<div[^>]*>([^<]+)</div>"  # player name in the inner <div>
    r"\s*</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"  # position
    r"<td[^>]*>.*?team-cap-on-light/(\d+)\.svg.*?<div[^>]*>([^<]+)</div>"  # team_id + name
    r".*?</td>\s*"
    r"<td[^>]*>.*?<div[^>]*>([^<]+)</div>"  # level
    r".*?</td>\s*"
    r"<td[^>]*>(\d+)</td>",  # age
    re.DOTALL,
)


def fetch_year(year: int, client: httpx.Client | None = None) -> str:
    """Fetch the raw HTML for one year's top-100 page."""
    owns = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=HEADERS)
    try:
        url = f"https://www.mlb.com/milb/prospects/{year}"
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.text
    finally:
        if owns:
            client.close()


def parse_rankings(html: str, year: int) -> list[dict[str, Any]]:
    """Extract (rank, player_id, name, position, team_id, team_name, level, age) rows."""
    out: list[dict[str, Any]] = []
    for match in ROW_PATTERN.finditer(html):
        rank = int(match.group(1))
        player_id = int(match.group(2))
        name = match.group(3).strip()
        position = match.group(4).strip()
        team_id = int(match.group(5))
        team_name = match.group(6).strip()
        level = match.group(7).strip()
        age = int(match.group(8))
        out.append(
            {
                "rank_year": year,
                "rank": rank,
                "mlb_player_id": player_id,
                "player_name": name,
                "position": position,
                "team_id": team_id,
                "team_name": team_name,
                "level": level,
                "age": age,
                "source": SOURCE,
            }
        )
    return out


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert prospect-rank rows; ignore PK conflicts."""
    if not rows:
        return 0
    import pandas as pd  # local

    df = pd.DataFrame(rows)
    conn.register("_staging_prospects", df)
    try:
        conn.execute(
            "INSERT INTO prospect_rankings "
            "(rank_year, rank, mlb_player_id, player_name, position, "
            "team_id, team_name, level, age, source) "
            "SELECT rank_year, rank, mlb_player_id, player_name, position, "
            "team_id, team_name, level, age, source "
            "FROM _staging_prospects "
            "ON CONFLICT (rank_year, mlb_player_id) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_prospects")
    return len(rows)


def ingest_year(year: int, client: httpx.Client | None = None) -> int:
    """End-to-end: fetch + parse + store one year's top-100."""
    html = fetch_year(year, client=client)
    rows = parse_rankings(html, year)
    if not rows:
        logger.warning("no prospect rows parsed for %d", year)
        return 0
    with db.connect() as conn:
        schemas.initialize(conn)
        teams.initialize(conn)
        upsert(conn, rows)
    logger.info("ingested %d prospect rows for year %d", len(rows), year)
    return len(rows)


def ingest_range(start_year: int, end_year: int) -> int:
    """Ingest a contiguous range of prospect-ranking years. Rate-limited politely."""
    import time

    total = 0
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=HEADERS) as client:
        for year in range(start_year, end_year + 1):
            try:
                total += ingest_year(year, client=client)
            except httpx.HTTPError as exc:
                logger.error("failed %d: %s", year, exc)
            time.sleep(RATE_LIMIT_SECONDS)
    return total
