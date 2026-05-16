"""Tests for the MLB Stats API coaches normalizer.

We test the dict-flattening shape (no network).
"""

from __future__ import annotations

from savage_trade_evaluator.ingest.coaches import _normalize


def test_normalize_canonical_payload() -> None:
    raw = {
        "jobCode": "MNGR",
        "job": "Manager",
        "person": {"id": 543335, "fullName": "A.J. Hinch"},
    }
    row = _normalize(team_id=117, season=2018, raw=raw)
    assert row == {
        "team_id": 117,
        "season": 2018,
        "job_code": "MNGR",
        "job_title": "Manager",
        "person_id": 543335,
        "person_name": "A.J. Hinch",
        "source": "mlb-stats-api",
    }


def test_normalize_falls_back_to_job_id_when_job_code_missing() -> None:
    """Older API responses sometimes use 'jobId' instead of 'jobCode'."""
    raw = {
        "jobId": "COAP",
        "job": "Pitching Coach",
        "person": {"id": 502067, "fullName": "Brent Strom"},
    }
    row = _normalize(team_id=117, season=2018, raw=raw)
    assert row["job_code"] == "COAP"
    assert row["person_name"] == "Brent Strom"


def test_normalize_tolerates_missing_person() -> None:
    raw = {"jobCode": "MNGR"}
    row = _normalize(team_id=117, season=2018, raw=raw)
    assert row["person_id"] is None
    assert row["person_name"] is None


def test_normalize_uses_question_mark_for_missing_job_code() -> None:
    raw = {"job": "Mystery"}
    row = _normalize(team_id=117, season=2018, raw=raw)
    assert row["job_code"] == "?"
