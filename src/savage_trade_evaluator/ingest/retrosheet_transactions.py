"""Ingest pre-2010 trade transactions from Retrosheet's transaction database.

The MLB Stats API gives us 2010+ transactions; Retrosheet fills 1880-2022.
Critical for the R-09/R-10 sample-size bottleneck — adds ~5,300 pre-2010
trade legs that V1 multilevel models need to detect per-org effects.

Source: https://www.retrosheet.org/transactions/tranDB.zip
Format documented in the bundled readme.txt. CSV-ish with quoted strings
and trailing whitespace on type codes. Each row is one player-movement;
multi-player trades share the same transaction-id.

Player ID mapping uses the Chadwick Register (via pybaseball) to bridge
Retrosheet's 8-char IDs (e.g. ``presr001``) to MLB Stats API integer
player IDs (e.g. 519151 for Ryan Pressly). Team codes are mapped via a
hand-coded dict since Retrosheet uses different abbreviations than
B-Ref / MLB Stats API (NYA vs NYY, CHN vs CHC, etc.).

Pressly trade verified: transaction 86280, 2018-07-27, three legs
(presr001 MIN->HOU, alcaj001 HOU->MIN, celeg001 HOU->MIN).
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

from savage_trade_evaluator.storage import db, schemas, teams

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "retrosheet"
TRANDB_URL = "https://www.retrosheet.org/transactions/tranDB.zip"
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "static" / "retrosheet"
HTTP_TIMEOUT_SECONDS = 60.0

# Retrosheet transaction-IDs collide with the MLB Stats API integer-ID space.
# Add a large offset so we can store both sources in one table without PK
# conflicts. 10^10 is well above any MLB Stats API transaction-id we have.
RETROSHEET_TRANSACTION_ID_OFFSET = 10_000_000_000

# Retrosheet 3-char team codes -> our bref_code. Limited to the modern (post-1969
# expansion) set since the backtester scope is MLB-era. Pre-1958 NL teams (BRO,
# NY1, BSN) and defunct franchises are intentionally left unmapped; their rows
# will be dropped at view time for lacking a from/to team id.
RETROSHEET_TEAM_TO_BREF: dict[str, str] = {
    "ANA": "LAA",  # Angels 1997-2004 brand
    "ARI": "ARI",
    "ATL": "ATL",
    "BAL": "BAL",
    "BOS": "BOS",
    "CAL": "LAA",  # California Angels pre-1997
    "CHA": "CHW",
    "CHN": "CHC",
    "CIN": "CIN",
    "CLE": "CLE",
    "COL": "COL",
    "DET": "DET",
    "FLO": "MIA",  # Marlins pre-2012
    "HOU": "HOU",
    "KCA": "KCR",
    "LAA": "LAA",
    "LAN": "LAD",
    "MIA": "MIA",
    "MIL": "MIL",
    "MIN": "MIN",
    "MON": "WSN",  # Expos -> Nationals (2005)
    "NYA": "NYY",
    "NYN": "NYM",
    "OAK": "OAK",
    "PHI": "PHI",
    "PIT": "PIT",
    "SDN": "SDP",
    "SEA": "SEA",
    "SFN": "SFG",
    "SLN": "STL",
    "TBA": "TBR",
    "TEX": "TEX",
    "TOR": "TOR",
    "WAS": "WSN",
}


def _download_trandb(cache: Path) -> Path:
    """Download tranDB.zip to the cache dir (idempotent)."""
    cache.mkdir(parents=True, exist_ok=True)
    zip_path = cache / "tranDB.zip"
    if zip_path.exists() and zip_path.stat().st_size > 0:
        logger.info("retrosheet cache hit: %s", zip_path)
        return zip_path
    logger.info("downloading %s", TRANDB_URL)
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        r = client.get(TRANDB_URL, follow_redirects=True)
        r.raise_for_status()
        zip_path.write_bytes(r.content)
    logger.info("wrote %d bytes to %s", len(r.content), zip_path)
    return zip_path


def _read_tran_txt(zip_path: Path) -> str:
    """Extract tran.txt content from the zip in memory."""
    with zipfile.ZipFile(zip_path) as zf, zf.open("tran.txt") as f:
        return io.TextIOWrapper(f, encoding="latin-1").read()


def _strip_quoted(s: str) -> str:
    """Strip surrounding double-quotes and trim whitespace."""
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.strip()


def _parse_date(s: str) -> date | None:
    """Parse yyyymmdd, returning None for off-season placeholders."""
    s = _strip_quoted(s)
    if len(s) != 8 or not s.isdigit():
        return None
    y, m, d = int(s[0:4]), int(s[4:6]), int(s[6:8])
    if m == 0 or d == 0:
        # off-season ('0000' month-day) — use Jan 1 of that year as a proxy
        return date(y, 1, 1)
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _split_line(line: str) -> list[str]:
    """Naive CSV split — fields don't contain commas in this file."""
    return line.split(",")


def parse_trades(text: str) -> list[dict[str, Any]]:
    """Extract raw trade-type rows (type == 'T').

    Other transaction types (free agency, releases, drafts, etc.) are filtered
    here for V1 scope. Multi-leg trades share a transaction-id, which we
    pass through; leg ordering is preserved per file order.
    """
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        cols = _split_line(line)
        if len(cols) < 12:
            continue
        ttype = _strip_quoted(cols[7])
        if ttype != "T":
            continue
        dt = _parse_date(cols[0])
        if dt is None:
            continue
        tid = cols[5].strip()
        if not tid.isdigit():
            continue
        player_raw = _strip_quoted(cols[6])
        from_team = _strip_quoted(cols[8])
        to_team = _strip_quoted(cols[10])
        out.append(
            {
                "rs_transaction_id": int(tid),
                "date": dt,
                "season": dt.year,
                "rs_player_id": player_raw if len(player_raw) == 8 else None,
                "player_name_raw": player_raw,
                "from_team_rs": from_team or None,
                "to_team_rs": to_team or None,
            }
        )
    return out


def _load_chadwick_lookup() -> dict[str, tuple[int, str]]:
    """Return retrosheet_id -> (mlb_player_id, full_name) lookup via Chadwick register."""
    import pandas as pd  # local
    from pybaseball import chadwick_register

    df: pd.DataFrame = chadwick_register()
    df = df[df["key_retro"].notna() & df["key_mlbam"].notna()]
    out: dict[str, tuple[int, str]] = {}
    for row in df.itertuples(index=False):
        first = (row.name_first or "").strip() if isinstance(row.name_first, str) else ""
        last = (row.name_last or "").strip() if isinstance(row.name_last, str) else ""
        full = f"{first} {last}".strip() or row.key_retro
        out[row.key_retro] = (int(row.key_mlbam), full)
    return out


def _load_team_lookup(conn: duckdb.DuckDBPyConnection) -> dict[str, tuple[int, str]]:
    """Return bref_code -> (mlb_team_id, name) lookup."""
    rows = conn.execute("SELECT bref_code, mlb_team_id, name FROM teams").fetchall()
    return {bref: (int(mid), name) for bref, mid, name in rows}


def _normalize(
    raw: dict[str, Any],
    leg_index: int,
    chadwick: dict[str, tuple[int, str]],
    team_bref_to_mlb: dict[str, tuple[int, str]],
) -> dict[str, Any]:
    """Map a parsed Retrosheet row to our transactions schema."""
    mlb_pid: int | None = None
    player_name: str | None = raw["player_name_raw"] or None
    if raw["rs_player_id"]:
        bridge = chadwick.get(raw["rs_player_id"])
        if bridge is not None:
            mlb_pid, player_name = bridge

    from_id = None
    from_name = None
    if raw["from_team_rs"]:
        bref = RETROSHEET_TEAM_TO_BREF.get(raw["from_team_rs"])
        if bref and bref in team_bref_to_mlb:
            from_id, from_name = team_bref_to_mlb[bref]

    to_id = None
    to_name = None
    if raw["to_team_rs"]:
        bref = RETROSHEET_TEAM_TO_BREF.get(raw["to_team_rs"])
        if bref and bref in team_bref_to_mlb:
            to_id, to_name = team_bref_to_mlb[bref]

    return {
        "transaction_id": raw["rs_transaction_id"] + RETROSHEET_TRANSACTION_ID_OFFSET,
        "leg_index": leg_index,
        "date": raw["date"],
        "effective_date": None,
        "resolution_date": None,
        "type_code": "TR",  # matches the MLB Stats API filter in trade_views
        "type_desc": "Trade",
        "description": None,
        "from_team_id": from_id,
        "from_team_name": from_name,
        "to_team_id": to_id,
        "to_team_name": to_name,
        "player_id": mlb_pid,
        "player_name": player_name,
        "season": raw["season"],
        "source": SOURCE,
    }


def upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> int:
    """Insert transaction rows; ignore PK conflicts (idempotent reruns)."""
    if not rows:
        return 0
    import pandas as pd  # local

    df = pd.DataFrame(rows)
    conn.register("_staging_rs_trans", df)
    try:
        conn.execute(
            "INSERT INTO transactions "
            "(transaction_id, leg_index, date, effective_date, resolution_date, "
            "type_code, type_desc, description, from_team_id, from_team_name, "
            "to_team_id, to_team_name, player_id, player_name, season, source) "
            "SELECT transaction_id, leg_index, date, effective_date, resolution_date, "
            "type_code, type_desc, description, from_team_id, from_team_name, "
            "to_team_id, to_team_name, player_id, player_name, season, source "
            "FROM _staging_rs_trans "
            "ON CONFLICT (transaction_id, leg_index) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_rs_trans")
    return len(rows)


def ingest(end_year: int = 2009) -> int:
    """Ingest Retrosheet trades through ``end_year`` (defaults to pre-2010 only).

    Args:
        end_year: Last season to ingest. Default 2009 — Retrosheet covers
            up to 2022 but we trust MLB Stats API for 2010+ to avoid
            duplicate-trade attribution conflicts across sources.

    Returns:
        Number of leg-rows inserted.
    """
    zip_path = _download_trandb(CACHE_DIR)
    text = _read_tran_txt(zip_path)
    raw_rows = parse_trades(text)
    logger.info("parsed %d trade-leg rows total", len(raw_rows))

    raw_rows = [r for r in raw_rows if r["season"] <= end_year]
    logger.info("filtered to %d rows with season <= %d", len(raw_rows), end_year)

    # Assign leg_index within (transaction_id, file-order). Retrosheet preserves
    # the per-trade row ordering already.
    counter: dict[int, int] = {}
    for r in raw_rows:
        tid = r["rs_transaction_id"]
        r["__leg_index"] = counter.get(tid, 0)
        counter[tid] = counter[tid] + 1 if tid in counter else 1

    chadwick = _load_chadwick_lookup()
    logger.info("chadwick lookup: %d retro->mlb mappings", len(chadwick))

    with db.connect() as conn:
        schemas.initialize(conn)
        teams.initialize(conn)
        team_lookup = _load_team_lookup(conn)
        normalized = [_normalize(r, r["__leg_index"], chadwick, team_lookup) for r in raw_rows]
        n = upsert(conn, normalized)

    logger.info("ingested %d retrosheet trade-leg rows through season %d", n, end_year)
    return n
