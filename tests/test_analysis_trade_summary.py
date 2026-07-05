"""Hermetic tests for trade-summary counts against a fixture DuckDB file."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from savage_trade_evaluator.analysis.trade_summary import TradeScopeCount, trades_per_season
from savage_trade_evaluator.storage import db, trade_views
from savage_trade_evaluator.storage.schemas import DDL_STATEMENTS

_TRANSACTIONS_DDL = next(
    s for s in DDL_STATEMENTS if "CREATE TABLE IF NOT EXISTS transactions" in s
)

_INSERT = (
    "INSERT INTO transactions (transaction_id, leg_index, date, type_code, "
    "from_team_id, from_team_name, to_team_id, to_team_name, "
    "player_id, player_name, season, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def test_trade_scope_count_total_sums_seasons() -> None:
    count = TradeScopeCount(label="x", counts_by_season={2018: 3, 2019: 4})
    assert count.total() == 7


def test_trades_per_season_counts_affiliated_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "trades.db"
    conn = duckdb.connect(str(db_file))
    conn.execute(_TRANSACTIONS_DDL)
    conn.executemany(
        _INSERT,
        [
            (100, 0, "2018-07-27", "TR", 142, "Twins", 117, "Astros", 1, "A", 2018, "test"),
            (100, 1, "2018-07-27", "TR", 117, "Astros", 142, "Twins", 2, "B", 2018, "test"),
            # Non-MLB receiving team id — excluded from affiliated view.
            (101, 0, "2018-08-01", "TR", 117, "Astros", 5000, "Fresno", 3, "C", 2018, "test"),
            (104, 0, "2019-07-30", "TR", 121, "Mets", 141, "Blue Jays", 5, "D", 2019, "test"),
        ],
    )
    trade_views.create_all(conn)
    conn.close()

    monkeypatch.setattr(db, "DUCKDB_PATH", db_file)
    result = trades_per_season()
    assert result.label == "affiliated trades"
    assert result.counts_by_season == {2018: 1, 2019: 1}
    assert result.total() == 2
