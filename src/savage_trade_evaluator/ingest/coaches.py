"""Ingest team coaching staff from the MLB Stats API.

The ``/teams/{teamId}/coaches?season=YYYY`` endpoint returns the full coaching
staff for one team-season: manager, bench/hitting/pitching/bullpen/base coaches
plus assistants. This is the raw material for **coach-portability** features
(MVP Machine Ch 5 — when Hyers moved from LAD to BOS, the swing-coach edge
moved with him).

Coverage: 2010+ (full backtester era).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.config import MLB_STATS_API_BASE
from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb
    import pandas as pd

logger = logging.getLogger(__name__)

SOURCE = "mlb-stats-api"
HTTP_TIMEOUT_SECONDS = 30.0

# MLB Stats API team IDs for the 30 active franchises. Hardcoded to avoid a
# round-trip on every ingestion; matches the canonical mapping in storage/teams.py.
TEAM_IDS: tuple[int, ...] = (
    108,
    109,
    110,
    111,
    112,
    113,
    114,
    115,
    116,
    117,
    118,
    119,
    120,
    121,
    133,
    134,
    135,
    136,
    137,
    138,
    139,
    140,
    141,
    142,
    143,
    144,
    145,
    146,
    147,
    158,
)


def fetch_team_season(
    team_id: int, season: int, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Fetch coaching staff for one (team, season).

    Args:
        team_id: MLB Stats API team integer ID.
        season: 4-digit year.
        client: Optional pre-built ``httpx.Client``.

    Returns:
        Raw roster entries from the API (each represents one staff member).
    """
    owns_client = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        response = client.get(
            f"{MLB_STATS_API_BASE}/teams/{team_id}/coaches",
            params={"season": season},
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            client.close()

    roster: list[dict[str, Any]] = payload.get("roster", [])
    return roster


def _normalize(team_id: int, season: int, raw: dict[str, Any]) -> dict[str, Any]:
    person = raw.get("person") or {}
    return {
        "team_id": team_id,
        "season": season,
        "job_code": raw.get("jobCode") or raw.get("jobId") or "?",
        "job_title": raw.get("job"),
        "person_id": person.get("id"),
        "person_name": person.get("fullName"),
        "source": SOURCE,
    }


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert coach rows into DuckDB, ignoring primary-key conflicts."""
    if not rows:
        return 0
    import pandas as pd

    df: pd.DataFrame = pd.DataFrame(rows)
    conn.register("_staging_coaches", df)
    try:
        conn.execute(
            "INSERT INTO coaches "
            "(team_id, season, job_code, job_title, person_id, person_name, source) "
            "SELECT team_id, season, job_code, job_title, person_id, person_name, source "
            "FROM _staging_coaches "
            "ON CONFLICT (team_id, season, job_code, person_id) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_coaches")
    return len(rows)


def ingest_season(season: int) -> int:
    """Fetch coaching staff for every team in a given season and upsert.

    Args:
        season: 4-digit year. Coaches endpoint coverage starts ~2010.

    Returns:
        Number of staff rows attempted to insert.
    """
    total = 0
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        all_rows: list[dict[str, Any]] = []
        for tid in TEAM_IDS:
            raw = fetch_team_season(tid, season, client=client)
            all_rows.extend(_normalize(tid, season, r) for r in raw)
        total += len(all_rows)
        with db.connect() as conn:
            schemas.initialize(conn)
            upsert(conn, all_rows)
    logger.info("ingested %d coach rows for season %d", total, season)
    return total
