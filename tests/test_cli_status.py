"""Hermetic tests for the ``ste status`` command's error UX."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from savage_trade_evaluator.cli import app

runner = CliRunner()


def test_status_reports_missing_database(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "nope.db"
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", missing)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "ste init" in result.output
    assert str(missing) in result.output


def test_status_reports_uninitialized_schema(tmp_path: Path, monkeypatch) -> None:
    import duckdb

    db_path = tmp_path / "empty.db"
    duckdb.connect(str(db_path)).close()
    monkeypatch.setattr("savage_trade_evaluator.cli.db.DUCKDB_PATH", db_path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 1
    assert "ste init" in result.output
