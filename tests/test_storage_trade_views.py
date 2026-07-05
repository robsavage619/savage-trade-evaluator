"""Hermetic tests for the trade-event views over the transactions table."""

from __future__ import annotations

import duckdb

from savage_trade_evaluator.storage import trade_views
from savage_trade_evaluator.storage.schemas import DDL_STATEMENTS

_TRANSACTIONS_DDL = next(
    s for s in DDL_STATEMENTS if "CREATE TABLE IF NOT EXISTS transactions" in s
)

_INSERT = (
    "INSERT INTO transactions (transaction_id, leg_index, date, type_code, "
    "from_team_id, from_team_name, to_team_id, to_team_name, "
    "player_id, player_name, season, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

FIXTURE_ROWS: list[tuple[object, ...]] = [
    # Event 100: two-leg MLB-affiliated trade.
    (100, 0, "2018-07-27", "TR", 142, "Twins", 117, "Astros", 1, "Ryan Pressly", 2018, "test"),
    (100, 1, "2018-07-27", "TR", 117, "Astros", 142, "Twins", 2, "Jorge Alcala", 2018, "test"),
    # Event 101: trade involving a non-MLB team id (outside 100-199).
    (101, 0, "2018-08-01", "TR", 117, "Astros", 5000, "Fresno", 3, "Farm Guy", 2018, "test"),
    # Event 102: not a trade (free agency).
    (102, 0, "2018-08-02", "FA", 117, "Astros", 121, "Mets", 4, "FA Guy", 2018, "test"),
    # Event 103: trade leg with no player attached.
    (103, 0, "2018-08-03", "TR", 117, "Astros", 121, "Mets", None, None, 2018, "test"),
    # Event 104: affiliated trade in a later season.
    (104, 0, "2019-07-30", "TR", 121, "Mets", 141, "Blue Jays", 5, "Other Guy", 2019, "test"),
]


def _seeded_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(_TRANSACTIONS_DDL)
    conn.executemany(_INSERT, FIXTURE_ROWS)
    trade_views.create_all(conn)
    return conn


def test_trade_movements_keeps_only_complete_trade_legs() -> None:
    conn = _seeded_conn()
    rows = conn.execute("SELECT trade_event_id FROM trade_movements").fetchall()
    ids = [r[0] for r in rows]
    assert sorted(ids) == [100, 100, 101, 104]


def test_trade_events_aggregates_legs_per_event() -> None:
    conn = _seeded_conn()
    row = conn.execute(
        "SELECT player_count, player_ids FROM trade_events WHERE trade_event_id = 100"
    ).fetchone()
    assert row is not None
    assert row[0] == 2
    assert sorted(row[1]) == [1, 2]


def test_trade_events_one_row_per_event() -> None:
    conn = _seeded_conn()
    (n,) = conn.execute("SELECT COUNT(*) FROM trade_events").fetchone() or (None,)
    assert n == 3


def test_trade_events_affiliated_excludes_non_mlb_team_ids() -> None:
    conn = _seeded_conn()
    rows = conn.execute(
        "SELECT trade_event_id FROM trade_events_affiliated ORDER BY trade_event_id"
    ).fetchall()
    assert [r[0] for r in rows] == [100, 104]
