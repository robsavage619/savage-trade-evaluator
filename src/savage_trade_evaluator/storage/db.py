"""DuckDB connection helpers."""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import duckdb

from savage_trade_evaluator.config import DUCKDB_PATH

if TYPE_CHECKING:
    from collections.abc import Iterator


@contextmanager
def connect(
    path: Path | None = None,
    read_only: bool = False,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """Open a DuckDB connection scoped to a ``with`` block.

    Args:
        path: Database file path. Defaults to ``config.DUCKDB_PATH``.
        read_only: If True, open in read-only mode.

    Yields:
        An open DuckDB connection that is closed on context exit.
    """
    target = path or DUCKDB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(target), read_only=read_only)
    try:
        yield conn
    finally:
        conn.close()


_INSERT_RE = re.compile(r"INSERT INTO\s+(\w+)\s*\((.*?)\)\s*SELECT", re.IGNORECASE | re.DOTALL)
_CONFLICT_RE = re.compile(r"ON CONFLICT\s*\((.*?)\)\s*DO NOTHING", re.IGNORECASE | re.DOTALL)


def execute_refreshing(conn: duckdb.DuckDBPyConnection, sql: str) -> duckdb.DuckDBPyConnection:
    """Run ``INSERT ... SELECT ... ON CONFLICT (keys) DO NOTHING`` as an upsert instead.

    DO NOTHING keeps whatever a key first got, which freezes a current-season figure at
    its first ingest: a daily re-run adds new rows and leaves every existing one stale.
    This rewrites the conflict clause to update the columns the statement inserts (and
    ``ingested_at`` when the table has it), so a failed fetch leaves old rows alone and a
    good one refreshes them. Columns the statement does not insert are never touched.

    Args:
        conn: Open connection.
        sql: An insert-select with an ``ON CONFLICT (...) DO NOTHING`` clause.

    Returns:
        The connection, as ``conn.execute`` does.

    Raises:
        ValueError: If ``sql`` is not an insert-select with a DO NOTHING conflict clause.
    """
    insert, conflict = _INSERT_RE.search(sql), _CONFLICT_RE.search(sql)
    if insert is None or conflict is None:
        raise ValueError("expected INSERT INTO t (cols) SELECT ... ON CONFLICT (keys) DO NOTHING")
    table = insert.group(1)
    keys = {k.strip() for k in conflict.group(1).split(",")}
    sets = [
        f"{c} = EXCLUDED.{c}"
        for c in (c.strip() for c in insert.group(2).split(","))
        if c not in keys and c != "ingested_at"
    ]
    if any(r[0] == "ingested_at" for r in conn.execute(f"DESCRIBE {table}").fetchall()):
        sets.append("ingested_at = now()")  # a bare CURRENT_TIMESTAMP reads as a column here
    update = f"ON CONFLICT ({conflict.group(1)}) DO UPDATE SET {', '.join(sets)}"
    return conn.execute(sql[: conflict.start()] + update + sql[conflict.end() :])
