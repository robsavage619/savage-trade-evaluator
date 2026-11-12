"""Ingest MLB's official free-agent lists, 2010 to now.

``/api/v1/people/freeAgents?season=YYYY`` lists everyone who reached free agency
that offseason: the club they left, the date, the club and date they signed, and a
short note. The note is where the contract shape lives ("Three-Year Contract",
"Player Option Declined", "Club option exercised"). It never carries dollars.

This is the only reachable history of when control actually ended, which is what
the forecast's "seasons held" assumption has to be checked against. Rows for the
current offseason change as players sign, so writes go through ``execute_refreshing``.

The table is created here, not in ``storage/schemas.py``, while that file carries
uncommitted changes of its own.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pandas as pd

from savage_trade_evaluator.ingest.fetch import get_json, make_client
from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

SOURCE = "mlb-stats-api"
URL = "https://statsapi.mlb.com/api/v1/people/freeAgents?season={season}"
FIRST_SEASON = 2010
REQUEST_PAUSE_SECONDS = 0.5

DDL = """
CREATE TABLE IF NOT EXISTS mlb_free_agents (
    season INTEGER NOT NULL,
    mlb_player_id INTEGER NOT NULL,
    player_name VARCHAR,
    position VARCHAR,
    date_declared DATE NOT NULL,
    date_signed DATE,
    original_team_id INTEGER,
    original_team VARCHAR,
    new_team_id INTEGER,
    new_team VARCHAR,
    notes VARCHAR,
    contract_years INTEGER,
    is_minor_league BOOLEAN,
    option_type VARCHAR,
    option_decision VARCHAR,
    kind VARCHAR,
    source VARCHAR NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (season, mlb_player_id, date_declared)
)
"""

_YEAR_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}  # fmt: skip
_YEARS_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d{1,2})[- ]year", re.I
)


@dataclass(frozen=True)
class Note:
    """What a free agent's note says about the contract.

    Attributes:
        contract_years: Years, when the note states a length ("Three-Year Contract").
        is_minor_league: Whether it is a minor-league deal.
        option_type: ``player``, ``team``, ``mutual`` or ``vesting`` when an option is mentioned.
        option_decision: ``exercised`` or ``declined`` when the note says so.
        kind: ``trade``, ``waiver``, ``option_decision`` or ``free_agency``. The list also
            carries off-season trades and waiver claims, which are not contract endings.
    """

    contract_years: int | None
    is_minor_league: bool
    option_type: str | None
    option_decision: str | None
    kind: str


def parse_note(text: str | None) -> Note:
    """Read the contract shape out of a free-agent note.

    Args:
        text: The ``notes`` field, possibly empty.

    Returns:
        A :class:`Note`; fields the note does not state are None or False.
    """
    t = (text or "").lower()
    years = _YEARS_RE.search(t)
    if years:
        word = years.group(1).lower()
        count = _YEAR_WORDS.get(word) or int(word)
    else:
        count = None
    option = None
    for needle, kind in (
        ("player option", "player"),
        ("mutual option", "mutual"),
        ("vesting", "vesting"),
        ("club option", "team"),
        ("team option", "team"),
    ):
        if needle in t:
            option = kind
            break
    decision = "exercised" if "exercised" in t else "declined" if "declined" in t else None
    if "traded" in t:
        kind = "trade"
    elif "waiver" in t or "claimed" in t:
        kind = "waiver"
    elif decision and "option" in t:
        kind = "option_decision"
    else:
        kind = "free_agency"
    return Note(count, "minor league" in t, option, decision, kind)


def parse_free_agents(season: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten one season's response into rows.

    Args:
        season: The season requested.
        payload: Decoded JSON from the endpoint.

    Returns:
        One dict per player-declaration, keyed by the table's columns. Entries without
        a player id or a declared date are skipped; there is nothing to key them on.
    """
    rows: dict[tuple[int, int, str], dict[str, Any]] = {}
    for entry in payload.get("freeAgents", []):
        player = entry.get("player") or {}
        declared = entry.get("dateDeclared")
        if not player.get("id") or not declared:
            continue
        note = parse_note(entry.get("notes"))
        origin, new = entry.get("originalTeam") or {}, entry.get("newTeam") or {}
        key = (season, int(player["id"]), declared)
        rows[key] = {
            "season": season,
            "mlb_player_id": int(player["id"]),
            "player_name": player.get("fullName"),
            "position": (entry.get("position") or {}).get("abbreviation"),
            "date_declared": declared,
            "date_signed": entry.get("dateSigned"),
            "original_team_id": origin.get("id"),
            "original_team": origin.get("name"),
            "new_team_id": new.get("id"),
            "new_team": new.get("name"),
            "notes": entry.get("notes"),
            "contract_years": note.contract_years,
            "is_minor_league": note.is_minor_league,
            "option_type": note.option_type,
            "option_decision": note.option_decision,
            "kind": note.kind,
            "source": SOURCE,
        }
    return list(rows.values())


def ingest_season(client: httpx.Client, season: int) -> int:
    """Fetch and store one season's list. Returns rows written."""
    rows = parse_free_agents(season, get_json(client, URL.format(season=season)))
    if not rows:
        raise RuntimeError(f"free-agent list for {season} came back empty")
    frame = pd.DataFrame(rows)
    cols = ", ".join(frame.columns)
    with db.connect() as conn:
        conn.execute(DDL)
        conn.execute("ALTER TABLE mlb_free_agents ADD COLUMN IF NOT EXISTS kind VARCHAR")
        conn.register("_staging_fa", frame)
        try:
            db.execute_refreshing(
                conn,
                f"INSERT INTO mlb_free_agents ({cols}) SELECT {cols} FROM _staging_fa "
                "ON CONFLICT (season, mlb_player_id, date_declared) DO NOTHING",
            )
        finally:
            conn.unregister("_staging_fa")
    return len(rows)


def ingest_range(start: int = FIRST_SEASON, end: int | None = None) -> int:
    """Ingest each season in turn.

    Args:
        start: First season.
        end: Last season; defaults to the current year.

    Returns:
        Total rows written.

    Raises:
        RuntimeError: Naming the seasons that failed, after trying all of them.
    """
    end = end or pd.Timestamp.today().year
    total, failed = 0, []
    with make_client() as client:
        for season in range(start, end + 1):
            try:
                total += ingest_season(client, season)
            except (RuntimeError, ValueError) as exc:
                logger.error("free agents %d failed: %s", season, exc)
                failed.append(season)
            time.sleep(REQUEST_PAUSE_SECONDS)
    if failed:
        raise RuntimeError(f"free-agent seasons failed: {failed}")
    return total
