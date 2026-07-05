"""Hermetic tests for War Room brief persistence and inbox export."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from savage_trade_evaluator.warroom import briefs


@pytest.fixture()
def inbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    box = tmp_path / "inbox"
    monkeypatch.setattr(briefs, "INBOX_DIR", box)
    return box


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "briefs.db"


def _row_count(db_path: Path) -> int:
    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        row = conn.execute("SELECT COUNT(*) FROM war_room_briefs").fetchone()
        assert row is not None
        return int(row[0])
    finally:
        conn.close()


def test_save_brief_writes_row_and_inbox_file(inbox: Path, db_path: Path) -> None:
    out = briefs.save_brief("hou", {"headline": "go get relief"}, db_path=db_path)
    assert out == inbox / "HOU.json"
    payload = json.loads(out.read_text())
    assert payload == {"headline": "go get relief", "team": "HOU"}
    assert _row_count(db_path) == 1


def test_save_brief_upserts_same_team_and_day(inbox: Path, db_path: Path) -> None:
    when = date(2026, 7, 1)
    briefs.save_brief("HOU", {"headline": "old"}, as_of=when, db_path=db_path)
    out = briefs.save_brief("HOU", {"headline": "new"}, as_of=when, db_path=db_path)
    assert _row_count(db_path) == 1
    assert json.loads(out.read_text())["headline"] == "new"


def test_export_brief_returns_false_when_missing(inbox: Path, db_path: Path) -> None:
    assert briefs.export_brief("HOU", db_path=db_path) is False
    assert not (inbox / "HOU.json").exists()


def test_export_brief_writes_latest_by_date(inbox: Path, db_path: Path) -> None:
    briefs.save_brief("HOU", {"headline": "old"}, as_of=date(2026, 6, 1), db_path=db_path)
    briefs.save_brief("HOU", {"headline": "new"}, as_of=date(2026, 7, 1), db_path=db_path)
    (inbox / "HOU.json").unlink()

    assert briefs.export_brief("hou", db_path=db_path) is True
    assert json.loads((inbox / "HOU.json").read_text())["headline"] == "new"


def test_export_all_writes_one_file_per_team(inbox: Path, db_path: Path) -> None:
    briefs.save_brief("HOU", {"headline": "a"}, db_path=db_path)
    briefs.save_brief("BOS", {"headline": "b"}, db_path=db_path)
    for f in inbox.iterdir():
        f.unlink()

    assert briefs.export_all(db_path=db_path) == 2
    assert json.loads((inbox / "HOU.json").read_text())["team"] == "HOU"
    assert json.loads((inbox / "BOS.json").read_text())["team"] == "BOS"


def test_as_text_normalizes_json_column_values() -> None:
    assert briefs._as_text('{"a":1}') == '{"a":1}'
    assert briefs._as_text({"a": 1}) == '{"a":1}'
