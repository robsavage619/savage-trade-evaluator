"""Ingest team front-office personnel from Baseball Reference per-season team pages.

Each ``https://www.baseball-reference.com/teams/<CODE>/<YEAR>.shtml`` page has a
front-office block listing General Manager, President of Baseball Operations,
Manager, Farm Director, Scouting Director, Owner, etc. We parse that block and
land one row per (team, season, role, person).

This is the canonical raw material for **GM-behavior modeling** (D-09 / Phase 3)
and for "career-progression" features like *scouting director → GM* (e.g., Mike
Elias HOU 2018 scouting → BAL 2019 GM).

BR is rate-limited - keep this gentle. 30 teams x ~15 seasons = ~450 requests
for a full backtester-era ingest; we sleep between requests to stay polite.
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

import httpx

from savage_trade_evaluator.storage import db, schemas, teams

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "bref-team-page"
HTTP_TIMEOUT_SECONDS = 30.0
RATE_LIMIT_SECONDS = 3.5  # BR's documented limit is ~20/min; this is below

BR_BASE = "https://www.baseball-reference.com/teams"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; savage-trade-evaluator/0.1; research only) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# Roles we want to capture from BR's front-office block. The exact role label
# in the HTML is `<strong>{label}:</strong>` followed by one or more names.
TARGET_ROLES: frozenset[str] = frozenset(
    {
        "General Manager",
        "President of Baseball Operations",
        "President",
        "Manager",
        "Farm Director",
        "Scouting Director",
        "Owner",
        "Director of Player Development",
        "Director of Player Personnel",
        "Assistant General Manager",
        "Vice President of Baseball Operations",
        "Chairman",
    }
)

# BR sometimes packs multiple roles into one <p> block, separated only by
# &nbsp; (e.g., "Manager: Alex Cora &nbsp; President: David Dombrowski"). We
# split on every <strong>...</strong> tag pair to robustly recover one
# (role, body) per role.
ROLE_BODY_PATTERN = re.compile(
    r"<strong>\s*([^<:]+?)\s*:?\s*</strong>([^<]*(?:<a[^>]*>[^<]*</a>[^<]*)*)",
    re.DOTALL,
)


def fetch_team_season_html(bref_code: str, season: int, client: httpx.Client | None = None) -> str:
    """GET the BR per-season team page HTML for one (team, season)."""
    owns = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=HEADERS)
    try:
        url = f"{BR_BASE}/{bref_code}/{season}.shtml"
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
        return r.text
    finally:
        if owns:
            client.close()


def parse_front_office(html: str) -> list[tuple[str, str]]:
    """Extract (role, person_name) pairs from one BR team-season page.

    BR's per-season pages put one <strong>Role:</strong> tag per role, sometimes
    multiple roles in the same <p> block (e.g., "Manager: X &nbsp; President: Y").
    We iterate every <strong> match and take the text up to the next <strong>
    as that role's body.

    Args:
        html: Raw HTML of the team-season page.

    Returns:
        List of (role, person_name) pairs.
    """
    out: list[tuple[str, str]] = []
    for match in ROLE_BODY_PATTERN.finditer(html):
        role = match.group(1).strip()
        if role not in TARGET_ROLES:
            continue
        body = match.group(2)
        # strip nested tags + decode common entities
        text = re.sub(r"<[^>]+>", "", body)
        text = text.replace("&nbsp;", " ").replace("&amp;", "&")
        # strip parenthetical content like "(92-71)" or "(President of Baseball Ops)"
        text = re.sub(r"\([^)]*\)", "", text)
        # roles can have multiple people (comma- or "and"-separated)
        for raw in re.split(r",|\band\b|\n|;", text):
            cleaned = raw.strip(" \t.;:")
            if not cleaned or len(cleaned) < 3 or not cleaned[0].isupper():
                continue
            if cleaned.endswith(":") or "/" in cleaned:
                continue
            out.append((role, cleaned))
    return out


def ingest_team_season(
    team_id: int, bref_code: str, season: int, client: httpx.Client | None = None
) -> int:
    """Fetch + parse + store one team-season front-office snapshot.

    Args:
        team_id: MLB Stats API integer team id.
        bref_code: Baseball Reference team code (e.g., 'HOU').
        season: 4-digit year.
        client: Optional shared httpx.Client.

    Returns:
        Number of rows written.
    """
    html = fetch_team_season_html(bref_code, season, client=client)
    pairs = parse_front_office(html)
    if not pairs:
        logger.warning("no front-office rows parsed for %s %d", bref_code, season)
        return 0

    rows = [
        {
            "team_id": team_id,
            "bref_code": bref_code,
            "season": season,
            "role": role,
            "person_name": name,
            "source": SOURCE,
        }
        for role, name in pairs
    ]
    with db.connect() as conn:
        schemas.initialize(conn)
        teams.initialize(conn)
        _upsert(conn, rows)
    return len(rows)


def _upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, object]]) -> int:
    import pandas as pd  # local to avoid module-level dependency for HTTP-only paths

    df: pd.DataFrame = pd.DataFrame(rows)
    conn.register("_staging_fo", df)
    try:
        conn.execute(
            "INSERT INTO front_office "
            "(team_id, bref_code, season, role, person_name, source) "
            "SELECT team_id, bref_code, season, role, person_name, source "
            "FROM _staging_fo "
            "ON CONFLICT (team_id, season, role, person_name) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_fo")
    return len(rows)


def ingest_season_all_teams(season: int) -> int:
    """Loop over all 30 MLB teams for one season. Rate-limited per BR's guidelines."""
    with db.connect(read_only=True) as conn:
        teams_rows = conn.execute(
            "SELECT mlb_team_id, bref_code FROM teams ORDER BY mlb_team_id"
        ).fetchall()

    total = 0
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers=HEADERS) as client:
        for team_id, bref_code in teams_rows:
            try:
                n = ingest_team_season(team_id, bref_code, season, client=client)
                total += n
                logger.info("ingested %s %d -> %d rows", bref_code, season, n)
            except httpx.HTTPError as exc:
                logger.error("failed %s %d: %s", bref_code, season, exc)
            time.sleep(RATE_LIMIT_SECONDS)
    return total
