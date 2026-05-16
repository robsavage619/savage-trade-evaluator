"""Ingest MLB Draft picks per year from the MLB Stats API.

Endpoint: ``/api/v1/draft/<year>``. Returns every drafted pick with rich
metadata: ``pickNumber``, ``pickRound``, ``rank`` (overall ranking), ``pickValue``
($ slot value), ``signingBonus`` (actual signed $), ``scoutingReport``,
``school``, ``team``, ``person.id`` (MLB Stats API player ID — joinable to
our trade and bWAR data).

This is the *practical* prospect-pedigree feature for the V1 trade-eval. The
MiLB Pipeline top-100 prospect list at ``mlb.com/milb/prospects/<year>`` is
the gold standard but lazy-loads via JS — would require Playwright.

Coverage probed 1990-2024:
* 1990: 100 rounds / 1,470 picks (the old uncapped era)
* 2000-2014: ~50 rounds / ~1,500 picks per year (slot-bonus pre-cap era)
* 2015-2019: ~40 rounds / ~1,200 picks (hard-cap settling in, D-11 era)
* 2020: 8 rounds / 160 picks (COVID-truncated, D-17 baseline shock)
* 2021-2024: ~20-26 rounds / ~600 picks (CBA-shortened post-2021)
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.config import MLB_STATS_API_BASE
from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)
SOURCE = "mlb-stats-api"
HTTP_TIMEOUT_SECONDS = 30.0


def fetch_year(year: int, client: httpx.Client | None = None) -> list[dict[str, Any]]:
    """Return a flat list of pick records for one draft year."""
    owns = client is None
    client = client or httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        r = client.get(f"{MLB_STATS_API_BASE}/draft/{year}")
        r.raise_for_status()
        payload = r.json()
    finally:
        if owns:
            client.close()

    out: list[dict[str, Any]] = []
    for round_obj in payload.get("drafts", {}).get("rounds", []):
        for pick in round_obj.get("picks", []):
            out.append(pick)
    return out


def _normalize(pick: dict[str, Any], year: int) -> dict[str, Any]:
    person = pick.get("person") or {}
    team = pick.get("team") or {}
    school = pick.get("school") or {}
    return {
        "draft_year": year,
        "pick_number": pick.get("pickNumber"),
        "pick_round": pick.get("pickRound"),
        "round_pick_number": pick.get("roundPickNumber"),
        "overall_rank": pick.get("rank"),
        "pick_value": pick.get("pickValue"),
        "signing_bonus": pick.get("signingBonus"),
        "is_drafted": pick.get("isDrafted"),
        "is_pass": pick.get("isPass"),
        "mlb_player_id": person.get("id"),
        "player_name": person.get("fullName"),
        "team_id": team.get("id"),
        "team_name": team.get("name"),
        "school_name": school.get("name"),
        "scouting_report": pick.get("scoutingReport"),
        "source": SOURCE,
    }


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert draft-pick rows; ignore PK conflicts."""
    if not rows:
        return 0
    import pandas as pd  # local

    df = pd.DataFrame(rows)
    # filter rows where pick_number is None (pass picks etc.) so we have a clean PK
    df = df[df["pick_number"].notna()]
    if df.empty:
        return 0
    conn.register("_staging_draft", df)
    try:
        conn.execute(
            "INSERT INTO draft_picks "
            "(draft_year, pick_number, pick_round, round_pick_number, overall_rank, "
            "pick_value, signing_bonus, is_drafted, is_pass, mlb_player_id, "
            "player_name, team_id, team_name, school_name, scouting_report, source) "
            "SELECT draft_year, pick_number, pick_round, round_pick_number, overall_rank, "
            "pick_value, signing_bonus, is_drafted, is_pass, mlb_player_id, "
            "player_name, team_id, team_name, school_name, scouting_report, source "
            "FROM _staging_draft "
            "ON CONFLICT (draft_year, pick_number) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_draft")
    return int(df.shape[0])


def ingest_year(year: int, client: httpx.Client | None = None) -> int:
    """End-to-end: fetch + normalize + store one draft year."""
    raw = fetch_year(year, client=client)
    rows = [_normalize(p, year) for p in raw]
    with db.connect() as conn:
        schemas.initialize(conn)
        n = upsert(conn, rows)
    logger.info("ingested %d draft picks for %d", n, year)
    return n


def ingest_range(start_year: int, end_year: int) -> int:
    """Ingest a contiguous range of draft years."""
    total = 0
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        for year in range(start_year, end_year + 1):
            try:
                total += ingest_year(year, client=client)
            except httpx.HTTPError as exc:
                logger.error("failed %d: %s", year, exc)
    return total
