"""Ingest MLB final-standings per season from the MLB Stats API.

Endpoint: ``/standings?leagueId=103,104&season=YYYY&standingsTypes=regularSeason``.
Returns 6 divisions of 5 teams each. Joins to our ``teams`` table by integer
team_id (which the MLB API gives us directly — no name-match heuristics).

(pybaseball.standings() was tried first but returns empty for 2010+ — BR
scrape fragility. The MLB Stats API source is the same one our transactions
adapter uses and is reliable.)
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.config import MLB_STATS_API_BASE
from savage_trade_evaluator.storage import db, schemas, teams

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)
SOURCE = "mlb-stats-api"
HTTP_TIMEOUT_SECONDS = 30.0


def fetch_season(season: int, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Pull final regular-season standings for one year.

    Returns:
        Flat list of per-team records with normalized keys: ``team_id``,
        ``wins``, ``losses``, ``win_pct``.
    """
    owns = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        r = client.get(
            f"{MLB_STATS_API_BASE}/standings",
            params={
                "leagueId": "103,104",
                "season": season,
                "standingsTypes": "regularSeason",
            },
        )
        r.raise_for_status()
        payload = r.json()
    finally:
        if owns:
            client.close()

    out: list[dict[str, Any]] = []
    for record in payload.get("records", []):
        for team_record in record.get("teamRecords", []):
            team = team_record.get("team") or {}
            out.append(
                {
                    "team_id": team.get("id"),
                    "season": season,
                    "wins": team_record.get("wins"),
                    "losses": team_record.get("losses"),
                    "win_pct": float(team_record.get("winningPercentage") or 0.0),
                }
            )
    return out


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert standings rows, joining to ``teams`` and ignoring PK conflicts."""
    if not rows:
        return 0
    import pandas as pd

    df = pd.DataFrame(rows)
    # join to teams to get bref_code
    team_map = conn.execute("SELECT mlb_team_id, bref_code FROM teams").df()
    merged = df.merge(team_map, left_on="team_id", right_on="mlb_team_id", how="inner")
    if merged.empty:
        return 0
    merged["source"] = SOURCE
    conn.register("_staging_std", merged)
    try:
        conn.execute(
            "INSERT INTO standings (team_id, bref_code, season, wins, losses, win_pct, source) "
            "SELECT team_id, bref_code, season, wins, losses, win_pct, source "
            "FROM _staging_std "
            "ON CONFLICT (team_id, season) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_std")
    return int(merged.shape[0])


def ingest_season(season: int) -> int:
    """End-to-end: fetch one season + store."""
    rows = fetch_season(season)
    with db.connect() as conn:
        schemas.initialize(conn)
        teams.initialize(conn)
        n = upsert(conn, rows)
    logger.info("ingested %d standings rows for season %d", n, season)
    return n
