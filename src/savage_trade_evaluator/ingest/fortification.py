"""Three high-value data-source ingest adapters added in the fortification pass.

Built from the systematic probe (scripts/probe_data_sources.py) that surveyed
24 candidate sources and identified three with the best leverage:

1. **Chadwick Register** (chadwickbureau/register on GitHub).
   ~26 split CSVs (people-0 through people-z). Provides:
   - birth_year/month/day → REAL age (currently proxied by years-since-debut)
   - mlbam ↔ retro ↔ bref ↔ fangraphs ID cross-walk
   - mlb_played_first/last, college play history
   - The single most valuable feature-engineering enabler we've added.

2. **Statcast catcher framing** (Baseball Savant leaderboard CSV).
   pybaseball's wrapper failed CSV-parsing earlier; direct fetch works.
   Per-catcher framing runs (rv_total) per year, by strike zone region.
   Lets us decompose "did the pitcher's xERA improve because of pitching
   dev or because their catcher framed better?"

3. **MLB Stats API awards** (MVP / Cy Young / ROY / Gold Glove / Silver Slugger).
   Per-season recipients across both leagues. Direct feature for prospect-
   pedigree work: "was this player drafted by the team that won an award
   for him later?" Also useful as a regime-quality signal.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import csv
import io
import logging
import math
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

CHADWICK_BASE = (
    "https://raw.githubusercontent.com/chadwickbureau/register/master/data/people-{shard}.csv"
)
CHADWICK_SHARDS = list("0123456789abcdef")  # 16 hex shards

SAVANT_FRAMING_URL = (
    "https://baseballsavant.mlb.com/leaderboard/catcher-framing?year={year}&team=&min=q&csv=true"
)

MLB_STATS_AWARDS_INDEX = "https://statsapi.mlb.com/api/v1/awards?sportId=1"
MLB_STATS_AWARDS_RECIPIENTS = (
    "https://statsapi.mlb.com/api/v1/awards/{award_id}/recipients?season={season}"
)

# Awards we care about for the V2 model. League MVP, Cy Young, ROY, GG, SS
# at the league level. Per-team awards are excluded as feature noise.
AWARDS_OF_INTEREST: tuple[str, ...] = (
    "ALMVP",
    "NLMVP",
    "ALCY",
    "NLCY",
    "MLBCY",
    "ALROY",
    "NLROY",
    "MLBROY",
    "ALSS",
    "NLSS",
    "ALGG",
    "NLGG",
    "MLGG",
    "ALCSMVP",
    "NLCSMVP",
    "WSMVP",
    "MLBHOF",
)


# === Chadwick Register ===


def _int_or_none(v: str) -> int | None:
    """Parse a possibly-empty integer field from a CSV row."""
    v = v.strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        try:
            f = float(v)
            return None if math.isnan(f) else int(f)
        except ValueError:
            return None


def _str_or_none(v: str) -> str | None:
    """Empty-string to None."""
    s = v.strip()
    return s or None


def fetch_chadwick_shard(client: httpx.Client, shard: str) -> list[dict[str, Any]]:
    """Fetch one Chadwick people-X.csv shard and parse to row dicts."""
    url = CHADWICK_BASE.format(shard=shard)
    r = client.get(url, timeout=60.0)
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    out: list[dict[str, Any]] = []
    for row in reader:
        mlbam = _int_or_none(row.get("key_mlbam", ""))
        if mlbam is None:
            continue  # only ingest rows with MLB IDs — the rest aren't useful
        out.append(
            {
                "mlb_player_id": mlbam,
                "retro_id": _str_or_none(row.get("key_retro", "")),
                "bref_id": _str_or_none(row.get("key_bbref", "")),
                "fangraphs_id": _str_or_none(row.get("key_fangraphs", "")),
                "name_first": _str_or_none(row.get("name_first", "")),
                "name_last": _str_or_none(row.get("name_last", "")),
                "name_given": _str_or_none(row.get("name_given", "")),
                "birth_year": _int_or_none(row.get("birth_year", "")),
                "birth_month": _int_or_none(row.get("birth_month", "")),
                "birth_day": _int_or_none(row.get("birth_day", "")),
                "death_year": _int_or_none(row.get("death_year", "")),
                "death_month": _int_or_none(row.get("death_month", "")),
                "death_day": _int_or_none(row.get("death_day", "")),
                "pro_played_first": _int_or_none(row.get("pro_played_first", "")),
                "pro_played_last": _int_or_none(row.get("pro_played_last", "")),
                "mlb_played_first": _int_or_none(row.get("mlb_played_first", "")),
                "mlb_played_last": _int_or_none(row.get("mlb_played_last", "")),
                "col_played_first": _int_or_none(row.get("col_played_first", "")),
                "col_played_last": _int_or_none(row.get("col_played_last", "")),
                "source": "chadwick-register",
            }
        )
    return out


def _upsert_chadwick(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Insert/upsert chadwick_register rows; ignore PK conflicts."""
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_chad", df)
    try:
        conn.execute(
            "INSERT INTO chadwick_register "
            "(mlb_player_id, retro_id, bref_id, fangraphs_id, name_first, name_last, "
            "name_given, birth_year, birth_month, birth_day, death_year, death_month, "
            "death_day, pro_played_first, pro_played_last, mlb_played_first, "
            "mlb_played_last, col_played_first, col_played_last, source) "
            "SELECT mlb_player_id, retro_id, bref_id, fangraphs_id, name_first, "
            "name_last, name_given, birth_year, birth_month, birth_day, death_year, "
            "death_month, death_day, pro_played_first, pro_played_last, "
            "mlb_played_first, mlb_played_last, col_played_first, col_played_last, "
            "source FROM _staging_chad "
            "ON CONFLICT (mlb_player_id) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_chad")


def ingest_chadwick_register() -> int:
    """Pull all 36 Chadwick register shards, upsert rows with MLB IDs."""
    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for shard in CHADWICK_SHARDS:
            rows = fetch_chadwick_shard(client, shard)
            _upsert_chadwick(conn, rows)
            total += len(rows)
            logger.info("chadwick shard %s: %d rows with mlb_id", shard, len(rows))
    logger.info("chadwick total: %d rows ingested", total)
    return total


# === Statcast catcher framing ===


def _safe_float(v: Any) -> float | None:
    """Coerce Savant CSV value to float, NaN-safe."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def fetch_catcher_framing_year(client: httpx.Client, year: int) -> list[dict[str, Any]]:
    """Direct CSV fetch from Savant (bypasses pybaseball's broken parser)."""
    url = SAVANT_FRAMING_URL.format(year=year)
    r = client.get(url, timeout=60.0)
    r.raise_for_status()
    text = r.text
    if text.startswith("﻿"):  # strip BOM
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict[str, Any]] = []
    for row in reader:
        pid_raw = row.get("id", "").strip()
        if not pid_raw:
            continue
        try:
            pid = int(pid_raw)
        except ValueError:
            continue
        out.append(
            {
                "player_id": pid,
                "player_name": row.get("name", "").strip().strip('"') or None,
                "year": year,
                "pitches": int(row["pitches"]) if row.get("pitches", "").strip() else None,
                "runs_total": _safe_float(row.get("rv_tot")),
                "strike_rate_total": _safe_float(row.get("pct_tot")),
                "rv_11": _safe_float(row.get("rv_11")),
                "pct_11": _safe_float(row.get("pct_11")),
                "rv_12": _safe_float(row.get("rv_12")),
                "pct_12": _safe_float(row.get("pct_12")),
                "rv_13": _safe_float(row.get("rv_13")),
                "pct_13": _safe_float(row.get("pct_13")),
                "rv_14": _safe_float(row.get("rv_14")),
                "pct_14": _safe_float(row.get("pct_14")),
                "rv_16": _safe_float(row.get("rv_16")),
                "pct_16": _safe_float(row.get("pct_16")),
                "rv_17": _safe_float(row.get("rv_17")),
                "pct_17": _safe_float(row.get("pct_17")),
                "rv_18": _safe_float(row.get("rv_18")),
                "pct_18": _safe_float(row.get("pct_18")),
                "rv_19": _safe_float(row.get("rv_19")),
                "pct_19": _safe_float(row.get("pct_19")),
                "source": "baseball-savant",
            }
        )
    return out


def _upsert_catcher_framing(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Insert/upsert catcher framing rows."""
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_cf", df)
    try:
        cols = (
            "player_id, player_name, year, pitches, runs_total, strike_rate_total, "
            "rv_11, pct_11, rv_12, pct_12, rv_13, pct_13, rv_14, pct_14, "
            "rv_16, pct_16, rv_17, pct_17, rv_18, pct_18, rv_19, pct_19, source"
        )
        conn.execute(
            f"INSERT INTO statcast_catcher_framing ({cols}) "
            f"SELECT {cols} FROM _staging_cf "
            "ON CONFLICT (player_id, year) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_cf")


def ingest_catcher_framing_range(start: int = 2015, end: int = 2024) -> int:
    """Ingest catcher framing for each year in range."""
    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for year in range(start, end + 1):
            try:
                rows = fetch_catcher_framing_year(client, year)
            except httpx.HTTPError as e:
                logger.warning("catcher framing %d failed: %s", year, e)
                continue
            _upsert_catcher_framing(conn, rows)
            total += len(rows)
            logger.info("catcher framing %d: %d rows", year, len(rows))
    return total


# === MLB Stats API Awards ===


def fetch_award_recipients(
    client: httpx.Client, award_id: str, season: int
) -> list[dict[str, Any]]:
    """Pull recipients for one award in one season."""
    url = MLB_STATS_AWARDS_RECIPIENTS.format(award_id=award_id, season=season)
    r = client.get(url, timeout=30.0)
    if r.status_code != 200:
        return []
    data = r.json()
    out: list[dict[str, Any]] = []
    for rec in data.get("awards", []):
        player = rec.get("player") or {}
        team = rec.get("team") or {}
        pid = player.get("id")
        if pid is None:
            continue
        out.append(
            {
                "award_id": award_id,
                "award_name": rec.get("name"),
                "season": season,
                "player_id": int(pid),
                "player_name": player.get("nameFirstLast") or player.get("fullName"),
                "team_id": team.get("id"),
                "team_name": team.get("name"),
                "votes": rec.get("votes"),
                "source": "mlb-stats-api",
            }
        )
    return out


def _upsert_awards(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Insert/upsert mlb_awards rows."""
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_aw", df)
    try:
        conn.execute(
            "INSERT INTO mlb_awards "
            "(award_id, award_name, season, player_id, player_name, "
            "team_id, team_name, votes, source) "
            "SELECT award_id, award_name, season, player_id, player_name, "
            "team_id, team_name, votes, source "
            "FROM _staging_aw "
            "ON CONFLICT (award_id, season, player_id) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_aw")


def ingest_awards_range(start: int = 1990, end: int = 2024) -> int:
    """Ingest all AWARDS_OF_INTEREST for seasons in range."""
    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for season in range(start, end + 1):
            for award_id in AWARDS_OF_INTEREST:
                rows = fetch_award_recipients(client, award_id, season)
                _upsert_awards(conn, rows)
                total += len(rows)
            logger.info("awards season %d: cumulative rows %d", season, total)
    return total
