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
    """
    CREATE OR REPLACE VIEW trade_player_xwoba_window AS
    -- Statcast-era only (2015+). xwOBA is the regression-to-mean baseline that
    -- filters BABIP noise out of trade-outcome assessment. Returns NULL for
    -- pre-2015 trades or players without Savant coverage.
    SELECT
        t.trade_event_id,
        t.leg_index,
        t.date,
        t.trade_season,
        t.mlb_player_id,
        t.player_name,
        t.from_team_bref,
        t.to_team_bref,
        prior.est_woba AS xwoba_t_minus_1,
        same.est_woba  AS xwoba_t,
        t1.est_woba    AS xwoba_t_plus_1,
        t2.est_woba    AS xwoba_t_plus_2,
        t3.est_woba    AS xwoba_t_plus_3
    FROM trade_player_unified t
    LEFT JOIN statcast_batting_expected prior
        ON prior.player_id = t.mlb_player_id AND prior.year = t.trade_season - 1
    LEFT JOIN statcast_batting_expected same
        ON same.player_id  = t.mlb_player_id AND same.year  = t.trade_season
    LEFT JOIN statcast_batting_expected t1
        ON t1.player_id    = t.mlb_player_id AND t1.year    = t.trade_season + 1
    LEFT JOIN statcast_batting_expected t2
        ON t2.player_id    = t.mlb_player_id AND t2.year    = t.trade_season + 2
    LEFT JOIN statcast_batting_expected t3
        ON t3.player_id    = t.mlb_player_id AND t3.year    = t.trade_season + 3
    """,
    """
    CREATE OR REPLACE VIEW trade_player_xera_window AS
    -- Pitcher analog: xERA windows from Statcast pitching-expected. Lower is
    -- better. Returns NULL for non-pitcher trades or pre-2015 events.
    SELECT
        t.trade_event_id,
        t.leg_index,
        t.date,
        t.trade_season,
        t.mlb_player_id,
        t.player_name,
        t.from_team_bref,
        t.to_team_bref,
        prior.xera AS xera_t_minus_1,
        same.xera  AS xera_t,
        t1.xera    AS xera_t_plus_1,
        t2.xera    AS xera_t_plus_2,
        t3.xera    AS xera_t_plus_3
    FROM trade_player_unified t
    LEFT JOIN statcast_pitching_expected prior
        ON prior.player_id = t.mlb_player_id AND prior.year = t.trade_season - 1
    LEFT JOIN statcast_pitching_expected same
        ON same.player_id  = t.mlb_player_id AND same.year  = t.trade_season
    LEFT JOIN statcast_pitching_expected t1
        ON t1.player_id    = t.mlb_player_id AND t1.year    = t.trade_season + 1
    LEFT JOIN statcast_pitching_expected t2
        ON t2.player_id    = t.mlb_player_id AND t2.year    = t.trade_season + 2
    LEFT JOIN statcast_pitching_expected t3
        ON t3.player_id    = t.mlb_player_id AND t3.year    = t.trade_season + 3
    """,
    """
    CREATE OR REPLACE VIEW trade_with_context AS
    -- Joins naïve baseline surplus to per-team-season context features for
    -- both receiving and giving sides. This is the row shape the V2 model
    -- fits on: (surplus, receiver_features, giver_features) per trade event.
    SELECT
        nbr.trade_event_id,
        nbr.trade_season,
        nbr.outcome_window_years,
        nbr.team_bref AS receiver_bref,
        nbr.surplus,
        nbr.war_received,
        nbr.war_given_up,
        tsf.prior_year_war AS receiver_prior_year_war,
        tsf.org_dev_fit_pitching AS receiver_dev_fit_pitching,
        tsf.org_dev_fit_hitting AS receiver_dev_fit_hitting,
        tsf.prior_year_wins AS receiver_prior_year_wins,
        tsf.prior_year_pyth_pct AS receiver_prior_year_pyth_pct,
        tsf.org_pitcher_k_jump_3yr AS receiver_org_pitcher_k_jump_3yr,
        tsf.org_hitter_xwoba_jump_3yr AS receiver_org_hitter_xwoba_jump_3yr,
        tsf.coach_hitter_xwoba_jump_3yr AS receiver_coach_hitter_xwoba_jump_3yr
    FROM naive_baseline_results nbr
    LEFT JOIN team_season_features tsf
        ON tsf.bref_code = nbr.team_bref
        AND tsf.season = nbr.trade_season
    """,
    """
    CREATE OR REPLACE VIEW trade_player_arsenal_window AS
    -- Pitcher-arsenal percentile ranks at T-1 and T+1. The "did the receiving
    -- team's dev system change this pitcher's arsenal" question lives here.
    -- Higher percentile = better. Statcast-era only.
    SELECT
        t.trade_event_id,
        t.leg_index,
        t.date,
        t.trade_season,
        t.mlb_player_id,
        t.player_name,
        t.from_team_bref,
        t.to_team_bref,
        prior.fb_velocity   AS fb_velocity_t_minus_1,
        post.fb_velocity    AS fb_velocity_t_plus_1,
        prior.fb_spin       AS fb_spin_t_minus_1,
        post.fb_spin        AS fb_spin_t_plus_1,
        prior.curve_spin    AS curve_spin_t_minus_1,
        post.curve_spin     AS curve_spin_t_plus_1,
        prior.k_percent     AS k_percent_t_minus_1,
        post.k_percent      AS k_percent_t_plus_1,
        prior.bb_percent    AS bb_percent_t_minus_1,
        post.bb_percent     AS bb_percent_t_plus_1,
        prior.whiff_percent AS whiff_percent_t_minus_1,
        post.whiff_percent  AS whiff_percent_t_plus_1,
        prior.chase_percent AS chase_percent_t_minus_1,
        post.chase_percent  AS chase_percent_t_plus_1
    FROM trade_player_unified t
    LEFT JOIN statcast_pitcher_percentile_ranks prior
        ON prior.player_id = t.mlb_player_id AND prior.year = t.trade_season - 1
    LEFT JOIN statcast_pitcher_percentile_ranks post
        ON post.player_id  = t.mlb_player_id AND post.year  = t.trade_season + 1
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
