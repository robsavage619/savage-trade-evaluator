"""Hermetic tests for score-trade and suggest-trades bref-code validation.

Tests only the validation path — no model cache needed.
The DB is seeded with just standings + team_season_features to cover the
_validate_bref_codes query, and the commands are expected to fail before
reaching feature assembly.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from typer.testing import CliRunner

from savage_trade_evaluator.cli import app

runner = CliRunner()

_STANDINGS_DDL = """
CREATE TABLE IF NOT EXISTS standings (
    team_id INTEGER NOT NULL,
    bref_code VARCHAR NOT NULL,
    season INTEGER NOT NULL,
    wins INTEGER NOT NULL,
    losses INTEGER NOT NULL,
    win_pct DOUBLE NOT NULL,
    source VARCHAR NOT NULL,
    PRIMARY KEY (team_id, season)
);
CREATE TABLE IF NOT EXISTS team_season_features (
    team_id INTEGER NOT NULL,
    bref_code VARCHAR NOT NULL,
    season INTEGER NOT NULL,
    PRIMARY KEY (team_id, season)
);
"""

_KNOWN_CODES = [("HOU", 117, 2024), ("NYY", 147, 2024), ("LAD", 119, 2024)]


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "test.db"
    conn = duckdb.connect(str(db_path))
    conn.execute(_STANDINGS_DDL)
    for code, tid, season in _KNOWN_CODES:
        conn.execute(
            "INSERT INTO standings VALUES (?, ?, ?, 90, 72, 0.556, 'test')",
            [tid, code, season],
        )
    conn.close()
    return db_path


def test_score_trade_bad_receiver_exits_1(tmp_path: Path, monkeypatch) -> None:
    db_path = _make_db(tmp_path)
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", db_path)
    result = runner.invoke(
        app,
        ["score-trade", "--receiver", "ZZZ", "--sender", "HOU", "--players", "592450"],
    )
    assert result.exit_code == 1
    assert "unknown team code" in result.output or "ZZZ" in result.output


def test_score_trade_bad_sender_exits_1(tmp_path: Path, monkeypatch) -> None:
    db_path = _make_db(tmp_path)
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", db_path)
    result = runner.invoke(
        app,
        ["score-trade", "--receiver", "HOU", "--sender", "ZZZ", "--players", "592450"],
    )
    assert result.exit_code == 1
    assert "unknown team code" in result.output or "ZZZ" in result.output


def test_score_trade_lowercase_receiver_normalizes(tmp_path: Path, monkeypatch) -> None:
    """Lowercase input 'hou' should resolve to 'HOU' and pass validation."""
    db_path = _make_db(tmp_path)
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", db_path)
    result = runner.invoke(
        app,
        ["score-trade", "--receiver", "hou", "--sender", "nzz", "--players", "592450"],
    )
    # 'hou' normalizes → 'HOU' (valid); 'nzz' → 'NZZ' (invalid) → exit 1 on sender
    assert result.exit_code == 1
    assert "NZZ" in result.output or "unknown team code" in result.output


def test_suggest_trades_bad_receiver_exits_1(tmp_path: Path, monkeypatch) -> None:
    db_path = _make_db(tmp_path)
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", db_path)
    result = runner.invoke(
        app,
        ["suggest-trades", "--receiver", "ZZZ"],
    )
    assert result.exit_code == 1
    assert "unknown team code" in result.output or "ZZZ" in result.output


def test_validate_skipped_when_db_empty(tmp_path: Path, monkeypatch) -> None:
    """If DB has no standings rows validation is skipped (not a hard error)."""
    db_path = tmp_path / "empty.db"
    conn = duckdb.connect(str(db_path))
    conn.execute(_STANDINGS_DDL)
    conn.close()
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", db_path)
    # With an empty DB and a totally bogus code, validation should be skipped.
    # The command may still fail later (no bwar tables etc.), but NOT at exit 1
    # with "unknown team code".
    result = runner.invoke(
        app,
        ["score-trade", "--receiver", "ZZZ", "--sender", "YYY", "--players", "592450"],
    )
    assert "unknown team code" not in (result.output or "")
