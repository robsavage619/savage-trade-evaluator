"""Ingest FanGraphs The Board prospect FV grades from pre-scraped CSV cache.

FanGraphs publishes an annual preseason top-100 prospect list ("The Board")
with Future Value (FV) grades on the 20-80 scouting scale. The data is
accessible without login via Firecrawl stealth proxy for 2017-2024 but
there is no Python API key available for live scraping.

Workflow:
  1. Scrape: run ``scripts/parse_fg_prospects.py`` to populate
     ``data/prospect_fv_cache/fangraphs_{year}.csv`` (one-time).
  2. Ingest: ``ste ingest prospects`` reads from that cache into
     ``prospect_rankings``.

The view ``trade_acquired_prospect_fv`` (defined in schemas.py) joins these
grades to ``trade_player_unified`` using a normalized-name match, and computes
``receiver_acquired_avg_fv`` and ``receiver_acquired_max_fv`` per
(trade_event_id, receiver_bref).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "fangraphs-the-board"

DEFAULT_CACHE_DIR = Path(__file__).parent.parent.parent.parent / "data" / "prospect_fv_cache"


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert FV rows; ignore PK conflicts (rank_year, fangraphs_player_id)."""
    if not rows:
        return 0

    df = pd.DataFrame(rows)
    conn.register("_staging_fv", df)
    try:
        conn.execute(
            """
            INSERT INTO prospect_rankings
                (rank_year, rank, fangraphs_player_id, player_name, player_name_norm,
                 org, position, level, fv, risk, eta, source)
            SELECT
                rank_year, rank, fangraphs_player_id, player_name, player_name_norm,
                org, position, level, fv, risk, eta, source
            FROM _staging_fv
            ON CONFLICT (rank_year, fangraphs_player_id) DO NOTHING
            """
        )
    finally:
        conn.unregister("_staging_fv")
    return len(rows)


def ingest_year(year: int, cache_dir: Path | None = None) -> int:
    """Load one year's FV grades from the CSV cache into prospect_rankings."""
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    csv_path = cache_dir / f"fangraphs_{year}.csv"
    if not csv_path.exists():
        logger.warning("FV cache missing for %d: %s", year, csv_path)
        return 0

    df = pd.read_csv(csv_path, dtype={"fangraphs_player_id": str, "eta": "Int64"})
    df["source"] = SOURCE
    rows = df.to_dict(orient="records")

    with db.connect() as conn:
        schemas.initialize(conn)
        n = upsert(conn, rows)

    logger.info("ingested %d FV rows for %d", n, year)
    return n


def ingest_range(
    start_year: int = 2017,
    end_year: int = 2024,
    cache_dir: Path | None = None,
) -> int:
    """Load all cached FV grades for a range of years."""
    total = 0
    for year in range(start_year, end_year + 1):
        total += ingest_year(year, cache_dir=cache_dir)
    return total
