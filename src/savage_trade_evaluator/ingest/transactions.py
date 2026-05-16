"""Ingest MLB transactions (trades, releases, free-agent signings, etc.) from the MLB Stats API.

The MLB Stats API exposes a ``/transactions`` endpoint that returns every recorded
transaction in a date range. We hit it one season at a time for politeness and
straightforward provenance.

See https://statsapi.mlb.com/api/v1/transactions?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD
"""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.config import MLB_STATS_API_BASE
from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "mlb-stats-api"
HTTP_TIMEOUT_SECONDS = 30.0


def fetch_season(season: int, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Pull every recorded transaction for one MLB regular-season year.

    The MLB transactions feed is sparse outside the season window, but we use
    Jan 1 - Dec 31 to capture offseason FA signings and trades that occur after
    the World Series.

    Args:
        season: 4-digit year (e.g., ``2018``).
        client: Optional pre-constructed ``httpx.Client``. A new one is created
            and closed if not provided.

    Returns:
        Raw transaction dicts as returned by the API. Empty list if none.
    """
    start = date(season, 1, 1).isoformat()
    end = date(season, 12, 31).isoformat()
    params = {"startDate": start, "endDate": end}

    owns_client = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        response = client.get(f"{MLB_STATS_API_BASE}/transactions", params=params)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            client.close()

    transactions: list[dict[str, Any]] = payload.get("transactions", [])
    logger.info("fetched %d transactions for season %d", len(transactions), season)
    return transactions


def _parse_iso_date(raw: str | None) -> date | None:
    """Parse an ISO date string, tolerating ``None`` and partial values.

    The MLB API sometimes returns ``"2018-07-27T00:00:00Z"`` or just
    ``"2018-07-27"``. We accept either.
    """
    if not raw:
        return None
    iso_part = raw.split("T", 1)[0]
    try:
        return date.fromisoformat(iso_part)
    except ValueError:
        logger.warning("could not parse date %r", raw)
        return None


def _normalize(raw: dict[str, Any], season: int) -> dict[str, Any]:
    """Flatten one nested API record into a row matching the ``transactions`` table."""
    from_team = raw.get("fromTeam") or {}
    to_team = raw.get("toTeam") or {}
    person = raw.get("person") or {}

    return {
        "transaction_id": raw["id"],
        "date": _parse_iso_date(raw.get("date")),
        "effective_date": _parse_iso_date(raw.get("effectiveDate")),
        "resolution_date": _parse_iso_date(raw.get("resolutionDate")),
        "type_code": raw.get("typeCode") or "",
        "type_desc": raw.get("typeDesc"),
        "description": raw.get("description"),
        "from_team_id": from_team.get("id"),
        "from_team_name": from_team.get("name"),
        "to_team_id": to_team.get("id"),
        "to_team_name": to_team.get("name"),
        "player_id": person.get("id"),
        "player_name": person.get("fullName"),
        "season": season,
        "source": SOURCE,
    }


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert transaction rows into DuckDB, ignoring primary-key conflicts.

    Args:
        conn: Open DuckDB connection (schema already initialized).
        rows: Normalized rows from ``_normalize``.

    Returns:
        Number of rows actually inserted (excluding conflicts).
    """
    if not rows:
        return 0

    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    sql = (
        f"INSERT INTO transactions ({column_list}) VALUES ({placeholders}) "
        f"ON CONFLICT (transaction_id) DO NOTHING"
    )

    values = [[row[c] for c in columns] for row in rows]
    for row_values in values:
        conn.execute(sql, row_values)
    return len(values)


def ingest_season(season: int) -> int:
    """End-to-end: fetch one season's transactions and write them to DuckDB.

    Args:
        season: 4-digit year.

    Returns:
        Number of transaction rows written (new + already-present treated alike).
    """
    raw = fetch_season(season)
    rows = [_normalize(r, season) for r in raw]
    with db.connect() as conn:
        schemas.initialize(conn)
        upsert(conn, rows)
    logger.info("ingested season %d → %d transactions", season, len(rows))
    return len(rows)
