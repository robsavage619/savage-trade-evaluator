"""Ingest Retrosheet per-game logs (1871-2024).

Each season is one ZIP file from ``retrosheet.org/gamelogs/gl<YEAR>.zip``,
containing one comma-separated text file with 161 fields per game. We
ingest only the first 19 (date, teams, scores, day/night, park, attendance,
time) — enough for game-level team-context features. The other 140 fields
(detailed offensive/pitching/fielding box-score stats, umpire/manager IDs,
pitcher IDs, etc.) are loadable later if needed.

Format documented at https://www.retrosheet.org/gamelogs/glfields.txt.

Team bref aliasing reuses RETROSHEET_TEAM_TO_BREF from
``ingest/retrosheet_transactions`` — same upstream code mappings.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import io
import logging
import zipfile
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.ingest.retrosheet_transactions import RETROSHEET_TEAM_TO_BREF
from savage_trade_evaluator.storage import db, schemas, teams

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "retrosheet"
GL_URL = "https://www.retrosheet.org/gamelogs/gl{year}.zip"
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "static" / "retrosheet_gl"


def _download_year(client: httpx.Client, year: int) -> Path:
    """Download gl<year>.zip to cache (idempotent)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / f"gl{year}.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path
    r = client.get(GL_URL.format(year=year), follow_redirects=True, timeout=60.0)
    r.raise_for_status()
    zip_path.write_bytes(r.content)
    return zip_path


def _read_txt(zip_path: Path) -> str:
    """Extract the single .txt file in the zip."""
    with zipfile.ZipFile(zip_path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".txt"))
        with zf.open(name) as f:
            return io.TextIOWrapper(f, encoding="latin-1").read()


def _strip_quoted(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.strip()


def _int_or_none(s: str) -> int | None:
    s = s.strip()
    if not s or s == '""':
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _parse_date(s: str) -> date | None:
    """Yyyymmdd → date."""
    s = _strip_quoted(s)
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def _alias_team(retrosheet_code: str) -> str | None:
    """Map Retrosheet 3-char code to current bref_code via the shared dict."""
    return RETROSHEET_TEAM_TO_BREF.get(retrosheet_code)


def parse_year(text: str, year: int) -> list[dict[str, Any]]:
    """Parse all game-log rows from one year's CSV text."""
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        # naive split — Retrosheet has no embedded commas inside quoted strings
        cols = line.split(",")
        if len(cols) < 19:
            continue
        game_date = _parse_date(cols[0])
        if game_date is None:
            continue
        game_number = _strip_quoted(cols[1])
        visitor_retro = _strip_quoted(cols[3])
        home_retro = _strip_quoted(cols[6])
        visitor_bref = _alias_team(visitor_retro)
        home_bref = _alias_team(home_retro)
        if visitor_bref is None or home_bref is None:
            continue  # historical/independent team not in our map

        out.append(
            {
                "game_date": game_date,
                "game_number": game_number or "0",
                "season": year,
                "day_of_week": _strip_quoted(cols[2]),
                "visitor_team_bref": visitor_bref,
                "visitor_league": _strip_quoted(cols[4]),
                "visitor_game_number": _int_or_none(cols[5]),
                "home_team_bref": home_bref,
                "home_league": _strip_quoted(cols[7]),
                "home_game_number": _int_or_none(cols[8]),
                "visitor_score": _int_or_none(cols[9]),
                "home_score": _int_or_none(cols[10]),
                "game_length_outs": _int_or_none(cols[11]),
                "day_night": _strip_quoted(cols[12]),
                "park_id": _strip_quoted(cols[16]) or None,
                "attendance": _int_or_none(cols[17]),
                "game_time_minutes": _int_or_none(cols[18]),
                "source": SOURCE,
            }
        )
    return out


def _upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_gl", df)
    try:
        conn.execute(
            "INSERT INTO game_logs "
            "(game_date, game_number, season, day_of_week, visitor_team_bref, "
            "visitor_league, visitor_game_number, home_team_bref, home_league, "
            "home_game_number, visitor_score, home_score, game_length_outs, "
            "day_night, park_id, attendance, game_time_minutes, source) "
            "SELECT game_date, game_number, season, day_of_week, visitor_team_bref, "
            "visitor_league, visitor_game_number, home_team_bref, home_league, "
            "home_game_number, visitor_score, home_score, game_length_outs, "
            "day_night, park_id, attendance, game_time_minutes, source "
            "FROM _staging_gl "
            "ON CONFLICT (game_date, game_number, home_team_bref, visitor_team_bref) "
            "DO NOTHING"
        )
    finally:
        conn.unregister("_staging_gl")
    return len(rows)


def ingest_year(year: int, client: httpx.Client | None = None) -> int:
    """Fetch + parse + upsert one year's game logs."""
    owns = client is None
    client = client or httpx.Client()
    try:
        zip_path = _download_year(client, year)
    finally:
        if owns:
            client.close()
    text = _read_txt(zip_path)
    rows = parse_year(text, year)
    with db.connect() as conn:
        schemas.initialize(conn)
        teams.initialize(conn)
        n = _upsert(conn, rows)
    logger.info("game logs %d: %d rows ingested", year, n)
    return n


def ingest_range(start: int = 1990, end: int = 2024) -> int:
    """Ingest a contiguous range of game-log years."""
    total = 0
    with httpx.Client() as client:
        for year in range(start, end + 1):
            try:
                total += ingest_year(year, client=client)
            except httpx.HTTPError as exc:
                logger.error("failed game logs %d: %s", year, exc)
    return total
