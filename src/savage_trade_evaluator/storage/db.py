"""DuckDB connection helpers."""

from __future__ import annotations

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
