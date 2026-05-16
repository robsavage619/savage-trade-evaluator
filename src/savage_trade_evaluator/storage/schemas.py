"""Versioned DDL for the trade-eval DuckDB schemas.

Schemas evolve via additive migrations. Each table carries an ``ingested_at``
column for provenance and a ``source`` column naming the upstream system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


SCHEMA_VERSION = 1

DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id BIGINT PRIMARY KEY,
        date DATE NOT NULL,
        effective_date DATE,
        resolution_date DATE,
        type_code VARCHAR NOT NULL,
        type_desc VARCHAR,
        description VARCHAR,
        from_team_id INTEGER,
        from_team_name VARCHAR,
        to_team_id INTEGER,
        to_team_name VARCHAR,
        player_id INTEGER,
        player_name VARCHAR,
        season INTEGER NOT NULL,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_season ON transactions(season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type_code)
    """,
)


def initialize(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply all DDL idempotently and record the schema version.

    Args:
        conn: An open DuckDB connection.
    """
    for stmt in DDL_STATEMENTS:
        conn.execute(stmt)

    current = conn.execute("SELECT max(version) FROM schema_version").fetchone()
    if current is None or current[0] != SCHEMA_VERSION:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", [SCHEMA_VERSION])
        logger.info("schema initialized at version %d", SCHEMA_VERSION)
