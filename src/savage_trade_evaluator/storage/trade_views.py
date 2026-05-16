"""SQL views that present ``transactions`` rows as structured trade events.

The MLB Stats API stores one row per player movement, with multiple rows sharing
a ``transaction_id`` for multi-player or multi-team trades. These views give us
trade-event-level and player-movement-level access without rewriting the
underlying raw store.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


VIEW_STATEMENTS: tuple[str, ...] = (
    """
    CREATE OR REPLACE VIEW trade_movements AS
    SELECT
        transaction_id AS trade_event_id,
        leg_index,
        date,
        season,
        from_team_id,
        from_team_name,
        to_team_id,
        to_team_name,
        player_id,
        player_name,
        description
    FROM transactions
    WHERE type_code = 'TR'
      AND player_id IS NOT NULL
      AND from_team_id IS NOT NULL
      AND to_team_id IS NOT NULL
    """,
    """
    CREATE OR REPLACE VIEW trade_events AS
    SELECT
        trade_event_id,
        date,
        season,
        COUNT(*) AS player_count,
        LIST(DISTINCT player_id) AS player_ids,
        LIST(DISTINCT from_team_id) AS teams_giving,
        LIST(DISTINCT to_team_id) AS teams_receiving,
        ANY_VALUE(description) AS description
    FROM trade_movements
    GROUP BY trade_event_id, date, season
    """,
    """
    CREATE OR REPLACE VIEW trade_events_affiliated AS
    SELECT *
    FROM trade_events
    WHERE list_min(teams_giving) BETWEEN 100 AND 199
      AND list_max(teams_giving) BETWEEN 100 AND 199
      AND list_min(teams_receiving) BETWEEN 100 AND 199
      AND list_max(teams_receiving) BETWEEN 100 AND 199
    """,
)


def create_all(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or replace every trade-event view.

    Args:
        conn: Open DuckDB connection with the ``transactions`` table populated.
    """
    for stmt in VIEW_STATEMENTS:
        conn.execute(stmt)
