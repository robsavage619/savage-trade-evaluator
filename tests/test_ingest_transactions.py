"""Unit tests for the transactions ingest adapter.

These tests stay offline by stubbing the HTTP client; integration smoke-testing
against the live MLB Stats API is done via the CLI.
"""

from __future__ import annotations

from datetime import date

from savage_trade_evaluator.ingest.transactions import _normalize, _parse_iso_date


def test_parse_iso_date_handles_iso_datetime() -> None:
    assert _parse_iso_date("2018-07-27T00:00:00Z") == date(2018, 7, 27)


def test_parse_iso_date_handles_plain_iso() -> None:
    assert _parse_iso_date("2018-07-27") == date(2018, 7, 27)


def test_parse_iso_date_returns_none_for_missing() -> None:
    assert _parse_iso_date(None) is None
    assert _parse_iso_date("") is None


def test_parse_iso_date_returns_none_on_garbage() -> None:
    assert _parse_iso_date("not-a-date") is None


def test_normalize_flattens_nested_payload() -> None:
    raw = {
        "id": 12345,
        "date": "2018-07-27T00:00:00Z",
        "effectiveDate": "2018-07-27",
        "typeCode": "TR",
        "typeDesc": "Trade",
        "description": "Twins trade Pressly to Astros.",
        "fromTeam": {"id": 142, "name": "Minnesota Twins"},
        "toTeam": {"id": 117, "name": "Houston Astros"},
        "person": {"id": 519151, "fullName": "Ryan Pressly"},
    }

    row = _normalize(raw, season=2018)

    assert row["transaction_id"] == 12345
    assert row["date"] == date(2018, 7, 27)
    assert row["type_code"] == "TR"
    assert row["from_team_name"] == "Minnesota Twins"
    assert row["to_team_id"] == 117
    assert row["player_name"] == "Ryan Pressly"
    assert row["season"] == 2018
    assert row["source"] == "mlb-stats-api"


def test_normalize_tolerates_missing_nested_objects() -> None:
    raw = {
        "id": 99,
        "date": "2018-01-01",
        "typeCode": "ASG",
    }
    row = _normalize(raw, season=2018)
    assert row["from_team_id"] is None
    assert row["to_team_name"] is None
    assert row["player_id"] is None
