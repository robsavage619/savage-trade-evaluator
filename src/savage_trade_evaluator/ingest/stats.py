"""Ingest player-season stats from Baseball Reference (bWAR) and Baseball Savant (Statcast).

Two layers:

* **bWAR spine** via ``pybaseball.bwar_bat`` / ``pybaseball.bwar_pitch`` — one row
  per player-season-stint going back to 1871. Carries WAR, off/def components,
  WAR_rep, WAA, salary. The historical backbone.
* **Savant Statcast layer** via ``pybaseball.statcast_*_expected_stats`` and
  ``pybaseball.statcast_pitcher_percentile_ranks`` — modern era (2015+) only,
  but covers xwOBA, xERA, fastball velocity / spin, chase / whiff rates. The
  fuel for dev-system-fit features.

FanGraphs is intentionally *not* in this adapter — FG fronts a hostile
Cloudflare gate that requires headless-browser scraping. bWAR + Savant
together cover the V1 feature set.
"""

# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportAssignmentType=false

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd
import pybaseball as pb

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BWAR_SOURCE = "bref-bwar"
SAVANT_SOURCE = "baseball-savant"


_BWAR_BAT_COLS = {
    "mlb_ID": "mlb_id",
    "player_ID": "bref_id",
    "name_common": "name_common",
    "year_ID": "year_id",
    "team_ID": "team_id",
    "stint_ID": "stint_id",
    "lg_ID": "lg_id",
    "pitcher": "is_pitcher",
    "G": "g",
    "PA": "pa",
    "salary": "salary",
    "runs_above_avg": "runs_above_avg",
    "runs_above_avg_off": "runs_above_avg_off",
    "runs_above_avg_def": "runs_above_avg_def",
    "WAR_rep": "war_rep",
    "WAA": "waa",
    "WAR": "war",
}

_BWAR_PIT_COLS = {
    "mlb_ID": "mlb_id",
    "player_ID": "bref_id",
    "name_common": "name_common",
    "year_ID": "year_id",
    "team_ID": "team_id",
    "stint_ID": "stint_id",
    "lg_ID": "lg_id",
    "G": "g",
    "GS": "gs",
    "RA": "ra",
    "xRA": "xra",
    "BIP": "bip",
    "BIP_perc": "bip_perc",
    "salary": "salary",
    "ERA_plus": "era_plus",
    "WAR_rep": "war_rep",
    "WAA": "waa",
    "WAA_adj": "waa_adj",
    "WAR": "war",
}


def _ingest_bwar(df: pd.DataFrame, table: str, col_map: dict[str, str]) -> int:
    """Filter, rename, and upsert a bwar DataFrame into the named table.

    Args:
        df: Raw DataFrame from ``pb.bwar_bat`` / ``pb.bwar_pitch``.
        table: Destination table name.
        col_map: Mapping from raw bwar column name → target column name.

    Returns:
        Number of rows attempted to insert.
    """
    renamed = df[list(col_map.keys())].rename(columns=col_map).copy()
    renamed["source"] = BWAR_SOURCE
    renamed = renamed.dropna(subset=["bref_id", "year_id", "stint_id"])
    renamed["mlb_id"] = pd.to_numeric(renamed["mlb_id"], errors="coerce").astype("Int64")
    renamed["year_id"] = renamed["year_id"].astype(int)
    renamed["stint_id"] = renamed["stint_id"].astype(int)
    if "is_pitcher" in renamed.columns:
        renamed["is_pitcher"] = renamed["is_pitcher"].map({"Y": True, "N": False})

    cols = list(renamed.columns)
    col_list = ", ".join(cols)
    with db.connect() as conn:
        schemas.initialize(conn)
        conn.register("_staging_bwar", renamed)
        try:
            conn.execute(
                f"INSERT INTO {table} ({col_list}) "
                f"SELECT {col_list} FROM _staging_bwar "
                f"ON CONFLICT (bref_id, year_id, stint_id) DO NOTHING"
            )
        finally:
            conn.unregister("_staging_bwar")
    return len(renamed)


def ingest_bwar_batting() -> int:
    """Pull the full bWAR batting table (1871-present) and upsert into DuckDB."""
    df = pb.bwar_bat(return_all=False)
    n = _ingest_bwar(df, table="bwar_batting", col_map=_BWAR_BAT_COLS)
    logger.info("ingested %d bwar batting rows", n)
    return n


def ingest_bwar_pitching() -> int:
    """Pull the full bWAR pitching table (1871-present) and upsert into DuckDB."""
    df = pb.bwar_pitch(return_all=False)
    n = _ingest_bwar(df, table="bwar_pitching", col_map=_BWAR_PIT_COLS)
    logger.info("ingested %d bwar pitching rows", n)
    return n


def _ingest_savant_table(
    df: pd.DataFrame,
    table: str,
    name_col: str,
    rename_map: dict[str, str] | None = None,
) -> int:
    """Normalize a Savant DataFrame and upsert into the named table.

    Args:
        df: DataFrame as returned by a pybaseball Savant helper.
        table: Destination DuckDB table.
        name_col: Source column to map to ``player_name``.
        rename_map: Extra column renames to apply.

    Returns:
        Number of rows attempted to insert.
    """
    df = df.copy()
    if name_col != "player_name":
        df = df.rename(columns={name_col: "player_name"})
    if rename_map:
        df = df.rename(columns=rename_map)
    df["source"] = SAVANT_SOURCE
    df = df.dropna(subset=["player_id", "year"])
    df["player_id"] = df["player_id"].astype(int)
    df["year"] = df["year"].astype(int)

    with db.connect() as conn:
        schemas.initialize(conn)
        # only keep columns that exist on the target table; DuckDB does this
        # implicitly when we SELECT by name, so we drop unmapped Savant columns
        target_cols_row = conn.execute(f"DESCRIBE {table}").fetchall()
        target_cols = {r[0] for r in target_cols_row}
        keep = [c for c in df.columns if c in target_cols]
        df = df[keep]
        col_list = ", ".join(df.columns)
        conn.register("_staging_savant", df)
        try:
            conn.execute(
                f"INSERT INTO {table} ({col_list}) "
                f"SELECT {col_list} FROM _staging_savant "
                f"ON CONFLICT (player_id, year) DO NOTHING"
            )
        finally:
            conn.unregister("_staging_savant")
    return len(df)


def ingest_statcast_batting_expected(season: int, min_pa: int = 25) -> int:
    """Pull and store xwOBA / xBA / xSLG for hitters in one season.

    Args:
        season: 4-digit year. Statcast era is 2015+.
        min_pa: Minimum plate appearances filter forwarded to Savant.
    """
    df = pb.statcast_batter_expected_stats(season, minPA=str(min_pa))
    n = _ingest_savant_table(
        df, table="statcast_batting_expected", name_col="last_name, first_name"
    )
    logger.info("ingested %d statcast batting expected rows for %d", n, season)
    return n


def ingest_statcast_pitching_expected(season: int, min_pa: int = 25) -> int:
    """Pull and store xwOBA / xERA expected stats for pitchers in one season."""
    df = pb.statcast_pitcher_expected_stats(season, minPA=str(min_pa))
    n = _ingest_savant_table(
        df, table="statcast_pitching_expected", name_col="last_name, first_name"
    )
    logger.info("ingested %d statcast pitching expected rows for %d", n, season)
    return n


def ingest_statcast_pitcher_percentile_ranks(season: int) -> int:
    """Pull and store pitcher percentile ranks (velocity, spin, whiff%, etc.) for one season."""
    df = pb.statcast_pitcher_percentile_ranks(season)
    n = _ingest_savant_table(
        df,
        table="statcast_pitcher_percentile_ranks",
        name_col="player_name",
    )
    logger.info("ingested %d pitcher percentile-rank rows for %d", n, season)
    return n
