from __future__ import annotations

import duckdb
import pytest

from savage_trade_evaluator.storage.db import execute_refreshing

INSERT = (
    "INSERT INTO t (player_id, year, war) SELECT player_id, year, war FROM staged "
    "ON CONFLICT (player_id, year) DO NOTHING"
)


def _conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect()
    conn.execute(
        "CREATE TABLE t (player_id INTEGER, year INTEGER, war DOUBLE, note VARCHAR, "
        "ingested_at TIMESTAMP DEFAULT TIMESTAMP '2000-01-01', PRIMARY KEY (player_id, year))"
    )
    conn.execute("INSERT INTO t (player_id, year, war, note) VALUES (1, 2026, 1.0, 'keep me')")
    conn.execute("CREATE TABLE staged (player_id INTEGER, year INTEGER, war DOUBLE)")
    return conn


def test_existing_row_is_refreshed_and_new_row_is_added() -> None:
    conn = _conn()
    conn.execute("INSERT INTO staged VALUES (1, 2026, 3.0), (2, 2026, 0.5)")
    execute_refreshing(conn, INSERT)
    rows = conn.execute("SELECT player_id, war FROM t ORDER BY player_id").fetchall()
    assert rows == [(1, 3.0), (2, 0.5)]  # DO NOTHING would have left player 1 at 1.0


def test_columns_the_statement_does_not_insert_are_untouched() -> None:
    conn = _conn()
    conn.execute("INSERT INTO staged VALUES (1, 2026, 3.0)")
    execute_refreshing(conn, INSERT)
    row = conn.execute("SELECT note, ingested_at FROM t WHERE player_id = 1").fetchone()
    assert row is not None
    note, stamp = row
    assert note == "keep me"
    assert stamp.year > 2000  # the freshness stamp moves when the row is refreshed


def test_a_statement_that_is_not_an_insert_select_fails_loudly() -> None:
    with pytest.raises(ValueError, match="ON CONFLICT"):
        execute_refreshing(_conn(), "INSERT INTO t (player_id) SELECT 1")
