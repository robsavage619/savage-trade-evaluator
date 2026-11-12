from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import duckdb
import pytest

from savage_trade_evaluator.ingest import mlb_free_agents as fa

# Entries copied (trimmed) from the real 2026 response.
KING = {
    "player": {"id": 650633, "fullName": "Michael King"},
    "originalTeam": {"id": 135, "name": "San Diego Padres"},
    "newTeam": {"link": "/api/v1/teams/null"},
    "notes": "Player Option Declined",
    "dateDeclared": "2026-10-30",
    "position": {"abbreviation": "SP"},
}
ABNER = {
    "player": {"id": 691769, "fullName": "Philip Abner"},
    "originalTeam": {"id": 121, "name": "New York Mets"},
    "newTeam": {"id": 110, "name": "Baltimore Orioles"},
    "notes": "Claimed off waivers.",
    "dateDeclared": "2026-11-02",
    "position": {"abbreviation": "RP"},
}


@pytest.mark.parametrize(
    ("text", "years", "minors", "option", "decision", "kind"),
    [
        ("Player Option Declined", None, False, "player", "declined", "option_decision"),
        ("Three-Year Contract", 3, False, None, None, "free_agency"),
        ("Two-year contract", 2, False, None, None, "free_agency"),
        ("One year with a club option for 2017", 1, False, "team", None, "free_agency"),
        (
            "One year with with a vesting mutual option for 2017",
            1,
            False,
            "mutual",
            None,
            "free_agency",
        ),
        ("Club option exercised", None, False, "team", "exercised", "option_decision"),
        ("Club option declined.", None, False, "team", "declined", "option_decision"),
        (
            "Minor League Contract - Invitation to Spring Training",
            None,
            True,
            None,
            None,
            "free_agency",
        ),
        ("Claimed off waivers.", None, False, None, None, "waiver"),
        (None, None, False, None, None, "free_agency"),
        ("Traded with OF Trent Grisham for RHP Michael King", None, False, None, None, "trade"),
    ],
)
def test_notes_are_read_for_length_option_and_decision(
    text: str | None,
    years: int | None,
    minors: bool,
    option: str | None,
    decision: str | None,
    kind: str,
) -> None:
    note = fa.parse_note(text)
    assert (
        note.contract_years,
        note.is_minor_league,
        note.option_type,
        note.option_decision,
        note.kind,
    ) == (years, minors, option, decision, kind)


def test_entries_flatten_with_and_without_a_new_team() -> None:
    rows = {
        r["mlb_player_id"]: r for r in fa.parse_free_agents(2026, {"freeAgents": [KING, ABNER]})
    }
    assert rows[650633]["new_team"] is None and rows[650633]["option_type"] == "player"
    assert rows[650633]["original_team"] == "San Diego Padres" and rows[650633]["position"] == "SP"
    assert rows[691769]["new_team_id"] == 110 and rows[691769]["date_declared"] == "2026-11-02"


def test_entries_without_an_id_or_a_date_are_skipped_and_repeats_collapse() -> None:
    payload = {
        "freeAgents": [
            {"player": {}, "dateDeclared": "2026-11-02"},
            {**KING, "dateDeclared": None},
            KING,
            KING,
        ]
    }
    assert [r["mlb_player_id"] for r in fa.parse_free_agents(2026, payload)] == [650633]


def test_a_rerun_updates_a_signing_instead_of_keeping_the_first_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = duckdb.connect()

    @contextmanager
    def fake_connect(*a: Any, **k: Any) -> Any:
        yield conn

    monkeypatch.setattr(fa.db, "connect", fake_connect)

    class Client:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

    unsigned = {"freeAgents": [KING]}
    signed = {
        "freeAgents": [
            {
                **KING,
                "newTeam": {"id": 143, "name": "Philadelphia Phillies"},
                "dateSigned": "2026-12-01",
            }
        ]
    }
    for payload in (unsigned, signed):
        monkeypatch.setattr(fa, "get_json", lambda client, url, p=payload: p)
        fa.ingest_season(Client(payload), 2026)  # type: ignore[arg-type]
    row = conn.execute("SELECT new_team, date_signed FROM mlb_free_agents").fetchall()
    assert row == [("Philadelphia Phillies", __import__("datetime").date(2026, 12, 1))]
