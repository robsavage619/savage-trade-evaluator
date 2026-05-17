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


# === MLB Stats API People (batch /people endpoint) ===


MLB_PEOPLE_BATCH_URL = "https://statsapi.mlb.com/api/v1/people?personIds={ids}"
BATCH_SIZE = 100  # safe batch size for the API


def _parse_height(h: str | None) -> int | None:
    r"""Parse ``6' 4\"`` style height to total inches."""
    if not h:
        return None
    try:
        parts = h.replace('"', "").split("'")
        feet = int(parts[0].strip())
        inches = int(parts[1].strip()) if len(parts) > 1 else 0
        return feet * 12 + inches
    except (ValueError, IndexError):
        return None


def _parse_iso_date(s: str | None) -> str | None:
    """Return ISO date string or None."""
    if not s:
        return None
    return s[:10]  # 'YYYY-MM-DD' from possibly longer ISO datetime


def fetch_people_batch(client: httpx.Client, ids: list[int]) -> list[dict[str, Any]]:
    """Fetch one batch of people via the MLB Stats API ``/people`` endpoint."""
    id_str = ",".join(str(i) for i in ids)
    r = client.get(MLB_PEOPLE_BATCH_URL.format(ids=id_str), timeout=30.0)
    r.raise_for_status()
    data = r.json()
    out: list[dict[str, Any]] = []
    for p in data.get("people", []):
        pid = p.get("id")
        if pid is None:
            continue
        pos = p.get("primaryPosition") or {}
        out.append(
            {
                "mlb_player_id": int(pid),
                "full_name": p.get("fullName"),
                "birth_date": _parse_iso_date(p.get("birthDate")),
                "birth_city": p.get("birthCity"),
                "birth_state_province": p.get("birthStateProvince"),
                "birth_country": p.get("birthCountry"),
                "height_inches": _parse_height(p.get("height")),
                "weight_lbs": p.get("weight"),
                "bat_side": (p.get("batSide") or {}).get("code"),
                "pitch_hand": (p.get("pitchHand") or {}).get("code"),
                "primary_position_code": pos.get("code"),
                "primary_position_name": pos.get("name"),
                "primary_position_type": pos.get("type"),
                "mlb_debut_date": _parse_iso_date(p.get("mlbDebutDate")),
                "last_played_date": _parse_iso_date(p.get("lastPlayedDate")),
                "active": p.get("active"),
                "source": "mlb-stats-api",
            }
        )
    return out


def _upsert_people(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Insert/upsert mlb_people rows."""
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_pe", df)
    try:
        cols = (
            "mlb_player_id, full_name, birth_date, birth_city, birth_state_province, "
            "birth_country, height_inches, weight_lbs, bat_side, pitch_hand, "
            "primary_position_code, primary_position_name, primary_position_type, "
            "mlb_debut_date, last_played_date, active, source"
        )
        conn.execute(
            f"INSERT INTO mlb_people ({cols}) SELECT {cols} FROM _staging_pe "
            "ON CONFLICT (mlb_player_id) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_pe")


# === MLB Stats API team season stats ===


MLB_TEAM_STATS_URL = (
    "https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
    "?season={season}&stats=season&group={group}"
)


def _flt(v: Any) -> float | None:
    """Coerce arbitrary value to float, NaN-safe."""
    if v is None or v == "":
        return None
    try:
        s = str(v)
        # Avg might come back as ".257" (trim leading dot)
        if s.startswith("."):
            s = "0" + s
        f = float(s)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def fetch_team_season_stats(
    client: httpx.Client, team_id: int, season: int, group: str
) -> dict[str, Any] | None:
    """Fetch one (team, season, group) row. Returns None if no data."""
    r = client.get(
        MLB_TEAM_STATS_URL.format(team_id=team_id, season=season, group=group),
        timeout=30.0,
    )
    if r.status_code != 200:
        return None
    splits = r.json().get("stats", [{}])[0].get("splits", [])
    if not splits:
        return None
    stat = splits[0].get("stat", {})
    return {
        "team_id": team_id,
        "season": season,
        "stat_group": group,
        "games_played": stat.get("gamesPlayed"),
        "runs": stat.get("runs"),
        "hits": stat.get("hits"),
        "doubles": stat.get("doubles"),
        "triples": stat.get("triples"),
        "home_runs": stat.get("homeRuns"),
        "strike_outs": stat.get("strikeOuts"),
        "base_on_balls": stat.get("baseOnBalls"),
        "avg": _flt(stat.get("avg")),
        "obp": _flt(stat.get("obp")),
        "slg": _flt(stat.get("slg")),
        "ops": _flt(stat.get("ops")),
        "era": _flt(stat.get("era")),
        "whip": _flt(stat.get("whip")),
        "innings_pitched": _flt(stat.get("inningsPitched")),
        "earned_runs": stat.get("earnedRuns"),
        "stolen_bases": stat.get("stolenBases"),
        "caught_stealing": stat.get("caughtStealing"),
        "fielding_pct": _flt(stat.get("fielding")),
        "errors": stat.get("errors"),
        "source": "mlb-stats-api",
    }


def ingest_team_season_stats_range(start: int = 1990, end: int = 2024) -> int:
    """Ingest hitting/pitching/fielding aggregates per team per season."""
    # Get current 30 MLB teams (just iterate IDs 108-158 known set)
    team_ids = list(range(108, 122)) + list(range(133, 148)) + [158]

    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for season in range(start, end + 1):
            rows: list[dict[str, Any]] = []
            for team_id in team_ids:
                for group in ("hitting", "pitching", "fielding"):
                    row = fetch_team_season_stats(client, team_id, season, group)
                    if row is not None:
                        # team_bref enrichment via teams table
                        row["team_bref"] = None
                        rows.append(row)
            if not rows:
                continue
            import pandas as pd

            df = pd.DataFrame(rows)
            conn.register("_staging_ts", df)
            try:
                cols = (
                    "team_id, team_bref, season, stat_group, games_played, "
                    "runs, hits, doubles, triples, home_runs, strike_outs, "
                    "base_on_balls, avg, obp, slg, ops, era, whip, "
                    "innings_pitched, earned_runs, stolen_bases, caught_stealing, "
                    "fielding_pct, errors, source"
                )
                conn.execute(
                    f"INSERT INTO team_season_stats ({cols}) "
                    f"SELECT {cols} FROM _staging_ts "
                    "ON CONFLICT (team_id, season, stat_group) DO NOTHING"
                )
            finally:
                conn.unregister("_staging_ts")
            total += len(rows)
            logger.info("team stats season %d: cumulative %d", season, total)
    return total


# === MLB Stats API venues ===


MLB_VENUES_URL = "https://statsapi.mlb.com/api/v1/venues?hydrate=fieldInfo,location"


def _safe_int(v: Any) -> int | None:
    """Coerce arbitrary value to int or None."""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def ingest_mlb_venues() -> int:
    """Pull every MLB venue with hydrated fieldInfo + location."""
    with httpx.Client() as client:
        r = client.get(MLB_VENUES_URL, timeout=60.0)
        r.raise_for_status()
    data = r.json()
    rows: list[dict[str, Any]] = []
    for v in data.get("venues", []):
        loc = v.get("location") or {}
        fi = v.get("fieldInfo") or {}
        rows.append(
            {
                "venue_id": int(v.get("id")),
                "name": v.get("name"),
                "city": loc.get("city"),
                "state_abbrev": loc.get("stateAbbrev"),
                "country": loc.get("country"),
                "capacity": _safe_int(fi.get("capacity")),
                "turf_type": fi.get("turfType"),
                "roof_type": fi.get("roofType"),
                "left_field_ft": _safe_int(fi.get("leftLine")),
                "left_center_ft": _safe_int(fi.get("leftCenter")),
                "center_field_ft": _safe_int(fi.get("center")),
                "right_center_ft": _safe_int(fi.get("rightCenter")),
                "right_field_ft": _safe_int(fi.get("rightLine")),
                "active": v.get("active"),
                "season": v.get("season"),
                "source": "mlb-stats-api",
            }
        )

    with db.connect() as conn:
        schemas.initialize(conn)
        if rows:
            import pandas as pd

            df = pd.DataFrame(rows)
            conn.register("_staging_v", df)
            try:
                cols = (
                    "venue_id, name, city, state_abbrev, country, capacity, "
                    "turf_type, roof_type, left_field_ft, left_center_ft, "
                    "center_field_ft, right_center_ft, right_field_ft, "
                    "active, season, source"
                )
                conn.execute(
                    f"INSERT INTO mlb_venues ({cols}) SELECT {cols} FROM _staging_v "
                    "ON CONFLICT (venue_id) DO NOTHING"
                )
            finally:
                conn.unregister("_staging_v")
    logger.info("venues: %d rows ingested", len(rows))
    return len(rows)


# === Retrosheet park reference ===


PARKCODE_URL = "https://www.retrosheet.org/parkcode.txt"


def ingest_retrosheet_parks() -> int:
    """Pull Retrosheet's parkcode.txt — 261 historical parks with metadata."""
    with httpx.Client() as client:
        r = client.get(PARKCODE_URL, timeout=30.0)
        r.raise_for_status()
    text = r.text
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for row in reader:
        park_id = row.get("PARKID", "").strip()
        if not park_id:
            continue
        rows.append(
            {
                "park_id": park_id,
                "name": row.get("NAME", "").strip() or None,
                "aka": row.get("AKA", "").strip() or None,
                "city": row.get("CITY", "").strip() or None,
                "state": row.get("STATE", "").strip() or None,
                "start_date": row.get("START", "").strip() or None,
                "end_date": row.get("END", "").strip() or None,
                "league": row.get("LEAGUE", "").strip() or None,
                "notes": row.get("NOTES", "").strip() or None,
                "source": "retrosheet",
            }
        )

    with db.connect() as conn:
        schemas.initialize(conn)
        if rows:
            import pandas as pd

            df = pd.DataFrame(rows)
            conn.register("_staging_pk", df)
            try:
                conn.execute(
                    "INSERT INTO retrosheet_parks "
                    "(park_id, name, aka, city, state, start_date, end_date, "
                    "league, notes, source) "
                    "SELECT park_id, name, aka, city, state, start_date, end_date, "
                    "league, notes, source FROM _staging_pk "
                    "ON CONFLICT (park_id) DO NOTHING"
                )
            finally:
                conn.unregister("_staging_pk")
    logger.info("parks: %d rows ingested", len(rows))
    return len(rows)


# === Statcast pitch movement ===


SAVANT_PITCH_MOVEMENT = (
    "https://baseballsavant.mlb.com/leaderboard/pitch-movement"
    "?year={year}&team=&min=q&hand=&pitch_type={pitch_type}&csv=true"
)
# Major pitch types we care about (Savant codes)
PITCH_TYPES_TO_INGEST: tuple[str, ...] = (
    "FF",  # 4-seam fastball
    "SI",  # sinker
    "FC",  # cutter
    "SL",  # slider
    "ST",  # sweeper
    "SV",  # slurve
    "CU",  # curveball
    "KC",  # knuckle curve
    "CH",  # changeup
    "FS",  # splitter
    "FO",  # forkball
    "SC",  # screwball
)


def fetch_pitch_movement_year(
    client: httpx.Client, year: int, pitch_type: str
) -> list[dict[str, Any]]:
    """Fetch one (year, pitch_type) pair from Savant pitch-movement leaderboard."""
    url = SAVANT_PITCH_MOVEMENT.format(year=year, pitch_type=pitch_type)
    r = client.get(url, timeout=60.0)
    r.raise_for_status()
    text = r.text
    if text.startswith("﻿"):
        text = text[1:]
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict[str, Any]] = []
    for row in reader:
        pid_raw = row.get("pitcher_id", "").strip()
        if not pid_raw:
            continue
        try:
            pid = int(pid_raw)
        except ValueError:
            continue
        try:
            yr = int(row.get("year", "").strip())
        except ValueError:
            yr = year
        out.append(
            {
                "player_id": pid,
                "player_name": row.get("last_name, first_name", "").strip().strip('"') or None,
                "team_abbrev": row.get("team_name_abbrev", "").strip() or None,
                "year": yr,
                "pitch_hand": row.get("pitch_hand", "").strip() or None,
                "pitch_type": row.get("pitch_type", "").strip() or pitch_type,
                "pitch_name": row.get("pitch_type_name", "").strip() or None,
                "avg_speed": _safe_float(row.get("avg_speed")),
                "pitches_thrown": int(row["pitches_thrown"])
                if row.get("pitches_thrown", "").strip()
                else None,
                "pitch_usage_pct": _safe_float(row.get("pitch_per")),
                "vertical_break_inches": _safe_float(row.get("pitcher_break_z")),
                "league_vertical_break": _safe_float(row.get("league_break_z")),
                "diff_vertical": _safe_float(row.get("diff_z")),
                "induced_vertical": _safe_float(row.get("pitcher_break_z_induced")),
                "horizontal_break_inches": _safe_float(row.get("pitcher_break_x")),
                "league_horizontal_break": _safe_float(row.get("league_break_x")),
                "diff_horizontal": _safe_float(row.get("diff_x")),
                "percentile_diff_vertical": _safe_float(row.get("percent_rank_diff_z")),
                "percentile_diff_horizontal": _safe_float(row.get("percent_rank_diff_x")),
                "source": "baseball-savant",
            }
        )
    return out


def ingest_pitch_movement_range(start: int = 2015, end: int = 2024) -> int:
    """Ingest pitch movement for each (year, pitch_type) in range."""
    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for year in range(start, end + 1):
            for pt in PITCH_TYPES_TO_INGEST:
                try:
                    rows = fetch_pitch_movement_year(client, year, pt)
                except httpx.HTTPError:
                    continue
                if not rows:
                    continue
                import pandas as pd

                df = pd.DataFrame(rows)
                conn.register("_staging_pm", df)
                try:
                    cols = (
                        "player_id, player_name, team_abbrev, year, pitch_hand, "
                        "pitch_type, pitch_name, avg_speed, pitches_thrown, "
                        "pitch_usage_pct, vertical_break_inches, league_vertical_break, "
                        "diff_vertical, induced_vertical, horizontal_break_inches, "
                        "league_horizontal_break, diff_horizontal, "
                        "percentile_diff_vertical, percentile_diff_horizontal, source"
                    )
                    conn.execute(
                        f"INSERT INTO statcast_pitch_movement ({cols}) "
                        f"SELECT {cols} FROM _staging_pm "
                        "ON CONFLICT (player_id, year, pitch_type) DO NOTHING"
                    )
                finally:
                    conn.unregister("_staging_pm")
                total += len(rows)
            logger.info("pitch movement %d: cumulative %d", year, total)
    return total


# === MLB Stats API team rosters ===


MLB_TEAMS_URL = "https://statsapi.mlb.com/api/v1/teams?sportId=1&season={season}"
MLB_ROSTER_URL = (
    "https://statsapi.mlb.com/api/v1/teams/{team_id}/roster"
    "?rosterType={roster_type}&season={season}"
)


def fetch_team_rosters_for_season(
    client: httpx.Client, season: int, roster_type: str = "40Man"
) -> list[dict[str, Any]]:
    """Get every team's roster for one season."""
    teams_resp = client.get(MLB_TEAMS_URL.format(season=season), timeout=30.0)
    teams_resp.raise_for_status()
    teams_data = teams_resp.json()
    out: list[dict[str, Any]] = []
    for team in teams_data.get("teams", []):
        team_id = team.get("id")
        # Skip non-MLB teams (occasional cameos)
        if not team_id or not team.get("active"):
            continue
        sport = team.get("sport") or {}
        if sport.get("id") != 1:
            continue
        try:
            rr = client.get(
                MLB_ROSTER_URL.format(team_id=team_id, roster_type=roster_type, season=season),
                timeout=30.0,
            )
        except httpx.HTTPError:
            continue
        if rr.status_code != 200:
            continue
        roster = rr.json().get("roster", [])
        for r in roster:
            person = r.get("person") or {}
            position = r.get("position") or {}
            status = r.get("status") or {}
            pid = person.get("id")
            if pid is None:
                continue
            out.append(
                {
                    "team_id": int(team_id),
                    "team_bref": team.get("abbreviation"),
                    "season": season,
                    "roster_type": roster_type,
                    "player_id": int(pid),
                    "player_name": person.get("fullName"),
                    "position_code": position.get("code"),
                    "position_name": position.get("name"),
                    "status": status.get("description"),
                    "jersey_number": r.get("jerseyNumber"),
                    "source": "mlb-stats-api",
                }
            )
    return out


def ingest_rosters_range(start: int = 2010, end: int = 2024) -> int:
    """Ingest 40-man rosters for every team for each season in range."""
    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for season in range(start, end + 1):
            rows = fetch_team_rosters_for_season(client, season)
            if not rows:
                continue
            import pandas as pd

            df = pd.DataFrame(rows)
            conn.register("_staging_rs", df)
            try:
                cols = (
                    "team_id, team_bref, season, roster_type, player_id, "
                    "player_name, position_code, position_name, status, "
                    "jersey_number, source"
                )
                conn.execute(
                    f"INSERT INTO team_rosters ({cols}) SELECT {cols} FROM _staging_rs "
                    "ON CONFLICT (team_id, season, roster_type, player_id) DO NOTHING"
                )
            finally:
                conn.unregister("_staging_rs")
            total += len(rows)
            logger.info("rosters season %d: cumulative %d", season, total)
    return total


def ingest_people_for_all_bwar_players() -> int:
    """Pull /people data for every mlb_player_id that appears in our bWAR table."""
    with db.connect() as conn:
        schemas.initialize(conn)
        ids = [
            int(r[0])
            for r in conn.execute(
                "SELECT DISTINCT mlb_id FROM bwar_player_seasons WHERE mlb_id IS NOT NULL"
            ).fetchall()
        ]
    logger.info("fetching MLB /people for %d distinct ids in batches of %d", len(ids), BATCH_SIZE)

    total = 0
    with httpx.Client() as client, db.connect() as conn:
        schemas.initialize(conn)
        for i in range(0, len(ids), BATCH_SIZE):
            batch = ids[i : i + BATCH_SIZE]
            try:
                rows = fetch_people_batch(client, batch)
            except httpx.HTTPError as exc:
                logger.warning("batch %d-%d failed: %s", i, i + BATCH_SIZE, exc)
                continue
            _upsert_people(conn, rows)
            total += len(rows)
            if i % 2000 == 0:
                logger.info("processed %d/%d ids (cumulative %d)", i + BATCH_SIZE, len(ids), total)
    logger.info("people total: %d rows ingested", total)
    return total
