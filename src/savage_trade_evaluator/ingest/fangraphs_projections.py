"""Ingest FanGraphs Steamer projections as dated snapshots.

``fangraphs.com/api/projections`` returns the projection system's current numbers for
every player, with MLBAM ids and projected playing time (games, plate appearances,
innings). It has no archive: it answers with the present only. So each run is stored
under its ``as_of`` date, and history exists only from the first run onward.

This is an unofficial JSON endpoint, so the parser fails loudly on a changed shape
instead of storing a partial table. The table is created here, not in
``storage/schemas.py``, while that file carries uncommitted changes of its own.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import TYPE_CHECKING, Any

import pandas as pd

from savage_trade_evaluator.ingest.fetch import get_json, make_client
from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

SOURCE = "fangraphs-api"
URL = (
    "https://www.fangraphs.com/api/projections?type={system}&stats={kind}"
    "&pos=all&team=0&players=0&lg=all"
)
SYSTEMS = ("steamer",)
KINDS = ("bat", "pit")
REQUEST_PAUSE_SECONDS = 3.0
MIN_ROWS = {
    "bat": 1500,
    "pit": 1500,
}  # a response far below this is a broken fetch, not a quiet day

DDL = """
CREATE TABLE IF NOT EXISTS fg_projections (
    as_of DATE NOT NULL,
    system VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    mlb_player_id INTEGER NOT NULL,
    fg_player_id VARCHAR,
    player_name VARCHAR,
    team VARCHAR,
    position VARCHAR,
    g DOUBLE,
    gs DOUBLE,
    pa DOUBLE,
    ip DOUBLE,
    war DOUBLE,
    woba DOUBLE,
    wrc_plus DOUBLE,
    k_pct DOUBLE,
    bb_pct DOUBLE,
    era DOUBLE,
    fip DOUBLE,
    adp DOUBLE,
    source VARCHAR NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (as_of, system, kind, mlb_player_id)
)
"""

_FIELDS = {
    "G": "g", "GS": "gs", "PA": "pa", "IP": "ip", "WAR": "war", "wOBA": "woba",
    "wRC+": "wrc_plus", "K%": "k_pct", "BB%": "bb_pct", "ERA": "era", "FIP": "fip", "ADP": "adp",
}  # fmt: skip


def _num(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def parse_projections(
    as_of: date, system: str, kind: str, payload: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Turn the endpoint's list into table rows.

    Args:
        as_of: Snapshot date.
        system: Projection system, e.g. ``steamer``.
        kind: ``bat`` or ``pit``.
        payload: Decoded JSON.

    Returns:
        One row per player with an MLBAM id (rows without one cannot be joined to
        anything here and are dropped), de-duplicated on id.

    Raises:
        ValueError: If the payload is not a list of player records with the expected
            identity fields, or is too short to be a real response.
    """
    if not isinstance(payload, list) or len(payload) < MIN_ROWS[kind]:
        raise ValueError(
            f"{system} {kind}: expected a list of at least {MIN_ROWS[kind]}, got {_size(payload)}"
        )
    if not {"PlayerName", "xMLBAMID", "WAR"} <= payload[0].keys():
        raise ValueError(
            f"{system} {kind}: identity or WAR fields are missing; the endpoint changed"
        )
    rows: dict[int, dict[str, Any]] = {}
    for r in payload:
        mlbam = r.get("xMLBAMID")
        if not mlbam:
            continue
        rows[int(mlbam)] = {
            "as_of": as_of,
            "system": system,
            "kind": kind,
            "mlb_player_id": int(mlbam),
            "fg_player_id": str(r["playerids"]) if r.get("playerids") is not None else None,
            "player_name": r.get("PlayerName"),
            "team": r.get("Team"),
            "position": r.get("minpos"),
            **{col: _num(r.get(src)) for src, col in _FIELDS.items()},
            "source": SOURCE,
        }
    return list(rows.values())


def _size(payload: object) -> str:
    return f"{len(payload)} rows" if isinstance(payload, list) else type(payload).__name__


def ingest_snapshot(client: httpx.Client, as_of: date, system: str, kind: str) -> int:
    """Fetch and store one system and kind for ``as_of``. Returns rows written."""
    rows = parse_projections(
        as_of, system, kind, get_json(client, URL.format(system=system, kind=kind))
    )
    frame = pd.DataFrame(rows)
    cols = ", ".join(frame.columns)
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute(
            "DELETE FROM fg_projections WHERE as_of = ? AND system = ? AND kind = ?",
            [as_of, system, kind],
        )
        conn.register("_staging_fgp", frame)
        try:
            conn.execute(f"INSERT INTO fg_projections ({cols}) SELECT {cols} FROM _staging_fgp")
        finally:
            conn.unregister("_staging_fgp")
    return len(rows)


def ingest_all(as_of: date | None = None) -> int:
    """Snapshot every system and kind for one date; re-running a date replaces it.

    Raises:
        RuntimeError: Naming what failed, after trying everything.
    """
    as_of = as_of or date.today()
    total, failed = 0, []
    with make_client() as client:
        for system in SYSTEMS:
            for kind in KINDS:
                try:
                    total += ingest_snapshot(client, as_of, system, kind)
                except (RuntimeError, ValueError) as exc:
                    logger.error("fangraphs %s %s failed: %s", system, kind, exc)
                    failed.append(f"{system}/{kind}")
                time.sleep(REQUEST_PAUSE_SECONDS)
    if failed:
        raise RuntimeError(f"fangraphs projections failed: {failed}")
    return total
