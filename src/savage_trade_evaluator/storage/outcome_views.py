"""Trade-with-outcome views. Metric-agnostic: any future outcome stat can plug in.

The trade-eval thesis (D-01) does not pre-commit to a single outcome metric.
This module exposes the trade *structure* — which player went where, with team
mappings resolved across sources — and lets any downstream model layer compute
"what happened next" using whichever outcome stat is relevant.

Views provided:

* ``trade_player_unified``: one row per (trade_event, player_movement) joined
  to the canonical team mapping. Includes both MLB integer IDs and Baseball
  Reference codes, so it can join cleanly to bWAR (string team codes) or
  Statcast (MLB integer player IDs).
* ``bwar_player_seasons``: union of bwar_batting + bwar_pitching at the
  player-season-stint grain, tagged by role. The single "everything WAR" table.
* ``trade_player_war_window``: for every trade movement, expose the player's
  WAR in the years T-1 (the GM-knew baseline), T (split by stint), T+1,
  T+2, T+3 (realized outcome window). Default outcome metric = WAR; swap
  by editing this view or building a sibling with a different stat.

These are *views*, not materialized tables — DuckDB recomputes on demand. The
joins are cheap given the indexes we have on transactions and bwar_*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb


VIEW_STATEMENTS: tuple[str, ...] = (
    """
    CREATE OR REPLACE VIEW trade_player_unified AS
    SELECT
        tm.trade_event_id,
        tm.leg_index,
        tm.date,
        tm.season AS trade_season,
        tm.player_id AS mlb_player_id,
        tm.player_name,
        tm.from_team_id,
        from_team.bref_code AS from_team_bref,
        tm.from_team_name,
        tm.to_team_id,
        to_team.bref_code AS to_team_bref,
        tm.to_team_name,
        tm.description
    FROM trade_movements tm
    LEFT JOIN teams AS from_team ON tm.from_team_id = from_team.mlb_team_id
    LEFT JOIN teams AS to_team   ON tm.to_team_id   = to_team.mlb_team_id
    """,
    """
    CREATE OR REPLACE VIEW bwar_player_seasons AS
    SELECT
        'B' AS role,
        mlb_id, bref_id, name_common,
        year_id, team_id, stint_id, lg_id,
        g,
        pa,
        salary,
        war,
        war_rep,
        waa,
        runs_above_avg,
        runs_above_avg_off,
        runs_above_avg_def
    FROM bwar_batting
    UNION ALL
    SELECT
        'P' AS role,
        mlb_id, bref_id, name_common,
        year_id, team_id, stint_id, lg_id,
        g,
        NULL::INTEGER AS pa,
        salary,
        war,
        war_rep,
        waa,
        NULL::DOUBLE AS runs_above_avg,
        NULL::DOUBLE AS runs_above_avg_off,
        NULL::DOUBLE AS runs_above_avg_def
    FROM bwar_pitching
    """,
    """
    CREATE OR REPLACE VIEW trade_player_war_window AS
    WITH season_war AS (
        -- one row per (player, year): total WAR summed across roles & stints
        SELECT
            mlb_id,
            year_id,
            SUM(war)::DOUBLE AS war,
            SUM(g)::INTEGER AS g
        FROM bwar_player_seasons
        WHERE mlb_id IS NOT NULL
        GROUP BY mlb_id, year_id
    ),
    receiving_team_war AS (
        -- one row per (player, year, team): WAR earned with that specific team
        SELECT
            ps.mlb_id,
            ps.year_id,
            ps.team_id AS bref_code,
            SUM(ps.war)::DOUBLE AS war_with_receiver
        FROM bwar_player_seasons AS ps
        WHERE ps.mlb_id IS NOT NULL
        GROUP BY ps.mlb_id, ps.year_id, ps.team_id
    )
    SELECT
        t.trade_event_id,
        t.leg_index,
        t.date,
        t.trade_season,
        t.mlb_player_id,
        t.player_name,
        t.from_team_bref,
        t.to_team_bref,
        prior.war  AS war_t_minus_1,
        same.war   AS war_t_total,
        rcvr.war_with_receiver AS war_t_with_receiver,
        t1.war     AS war_t_plus_1,
        t2.war     AS war_t_plus_2,
        t3.war     AS war_t_plus_3
    FROM trade_player_unified t
    LEFT JOIN season_war prior ON prior.mlb_id = t.mlb_player_id
                              AND prior.year_id = t.trade_season - 1
    LEFT JOIN season_war same  ON same.mlb_id  = t.mlb_player_id
                              AND same.year_id  = t.trade_season
    LEFT JOIN season_war t1    ON t1.mlb_id    = t.mlb_player_id
                              AND t1.year_id    = t.trade_season + 1
    LEFT JOIN season_war t2    ON t2.mlb_id    = t.mlb_player_id
                              AND t2.year_id    = t.trade_season + 2
    LEFT JOIN season_war t3    ON t3.mlb_id    = t.mlb_player_id
                              AND t3.year_id    = t.trade_season + 3
    LEFT JOIN receiving_team_war rcvr
                              ON rcvr.mlb_id    = t.mlb_player_id
                              AND rcvr.year_id  = t.trade_season
                              AND rcvr.bref_code = t.to_team_bref
    """,
)


def create_all(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or replace every outcome view.

    Args:
        conn: Open DuckDB connection. Requires transactions, bwar_batting,
            bwar_pitching, teams, and trade_movements to already exist.
    """
    for stmt in VIEW_STATEMENTS:
        conn.execute(stmt)
