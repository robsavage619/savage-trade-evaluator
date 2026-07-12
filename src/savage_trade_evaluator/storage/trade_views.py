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
    # IL stints: pair each placement with the next activation for the same player.
    # Matching is positional (N-th placement ↔ N-th activation) — correct for the
    # common case; may mis-align for concurrent stints or re-assignments across levels.
    # Players still on the IL at query time have a NULL activation_date / NULL days_on_il.
    """
    CREATE OR REPLACE VIEW il_stints AS
    WITH placements AS (
        SELECT
            player_id,
            player_name,
            season,
            date AS placement_date,
            CASE
                WHEN description ILIKE '%60%day%' THEN 60
                WHEN description ILIKE '%15%day%' THEN 15
                WHEN description ILIKE '%10%day%' THEN 10
                WHEN description ILIKE '%7%day%'  THEN 7
                ELSE NULL
            END AS list_type_days,
            ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY date) AS stint_num
        FROM transactions
        WHERE type_desc = 'Status Change'
          AND player_id IS NOT NULL
          AND (description ILIKE '%placed%injured list%'
            OR description ILIKE '%placed%disabled list%')
    ),
    activations AS (
        SELECT
            player_id,
            date AS activation_date,
            ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY date) AS stint_num
        FROM transactions
        WHERE type_desc = 'Status Change'
          AND player_id IS NOT NULL
          AND (description ILIKE '%activated%injured list%'
            OR description ILIKE '%activated%disabled list%')
    )
    SELECT
        p.player_id,
        p.player_name,
        p.season,
        p.placement_date,
        a.activation_date,
        p.list_type_days,
        DATEDIFF('day', p.placement_date, a.activation_date) AS days_on_il
    FROM placements p
    LEFT JOIN activations a
        ON p.player_id = a.player_id
       AND a.stint_num = p.stint_num
    """,
    # Options usage: seasons in which a player appeared on an 'Optioned' transaction.
    # Counts distinct seasons, not individual option exercises within a season.
    """
    CREATE OR REPLACE VIEW player_option_years AS
    SELECT
        player_id,
        player_name,
        season,
        COUNT(*) AS times_optioned
    FROM transactions
    WHERE type_desc = 'Optioned'
      AND player_id IS NOT NULL
    GROUP BY player_id, player_name, season
    """,
)


def create_all(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or replace every trade-event view.

    Args:
        conn: Open DuckDB connection with the ``transactions`` table populated.
    """
    for stmt in VIEW_STATEMENTS:
        conn.execute(stmt)
