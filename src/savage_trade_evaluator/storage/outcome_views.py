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
    CREATE OR REPLACE VIEW trade_player_dev_signature AS
    -- Per (trade_event, receiving_team), aggregate the acquired players' pre-trade
    -- 2-year rate-based performance into a unified "acquired-player-quality" signal.
    -- WITHIN-team variation (different trades have different player mixes);
    -- satisfies the D-24 architectural rule against static team features.
    --
    -- Per-player measure (each player contributes ONE value regardless of position):
    --   hitters: avg of (runs_above_avg_off / pa) * 600 over (t-1, t-2), per-600-PA basis
    --   pitchers: avg of (era_plus - 100) / 10 over (t-1, t-2), SD-like deviation from avg
    -- These two are on roughly comparable scales (~-5 to +5 for both elite/replacement).
    --
    -- Per D-11 (components, not aggregate WAR). Pitchers use era_plus which is
    -- era- and park-adjusted with 1871+ coverage. Hitters use runs_above_avg_off
    -- which is offense-only (sidesteps DRS/UZR noise).
    WITH hitter_perf AS (
        SELECT mlb_id, year_id,
               (SUM(runs_above_avg_off) / NULLIF(SUM(pa), 0)) * 600.0 AS off_per_600
        FROM bwar_batting
        WHERE mlb_id IS NOT NULL AND pa >= 30
        GROUP BY mlb_id, year_id
    ),
    pitcher_perf AS (
        SELECT mlb_id, year_id,
               (AVG(era_plus) - 100.0) / 10.0 AS era_plus_dev
        FROM bwar_pitching
        WHERE mlb_id IS NOT NULL AND era_plus IS NOT NULL AND g >= 5
        GROUP BY mlb_id, year_id
    ),
    per_player_unified AS (
        -- Each player contributes one row with one value (hitter OR pitcher; if both,
        -- we average both — two-way players are rare and acceptable noise).
        SELECT
            tpu.trade_event_id,
            tpu.to_team_bref AS receiver_bref,
            tpu.mlb_player_id,
            AVG(COALESCE(h_prior.off_per_600, h_prior2.off_per_600,
                         p_prior.era_plus_dev, p_prior2.era_plus_dev,
                         (h_prior.off_per_600 + p_prior.era_plus_dev) / 2.0)) AS quality_signal,
            -- explicit fallback chain: prefer t-1 if available, else t-2, else other class
            CASE
                WHEN h_prior.off_per_600 IS NOT NULL AND p_prior.era_plus_dev IS NOT NULL
                    THEN (h_prior.off_per_600 + p_prior.era_plus_dev) / 2.0
                WHEN h_prior.off_per_600 IS NOT NULL THEN h_prior.off_per_600
                WHEN p_prior.era_plus_dev IS NOT NULL THEN p_prior.era_plus_dev
                WHEN h_prior2.off_per_600 IS NOT NULL THEN h_prior2.off_per_600
                WHEN p_prior2.era_plus_dev IS NOT NULL THEN p_prior2.era_plus_dev
                ELSE NULL
            END AS pre_trade_quality
        FROM trade_player_unified tpu
        LEFT JOIN hitter_perf h_prior
            ON h_prior.mlb_id = tpu.mlb_player_id
            AND h_prior.year_id = tpu.trade_season - 1
        LEFT JOIN hitter_perf h_prior2
            ON h_prior2.mlb_id = tpu.mlb_player_id
            AND h_prior2.year_id = tpu.trade_season - 2
        LEFT JOIN pitcher_perf p_prior
            ON p_prior.mlb_id = tpu.mlb_player_id
            AND p_prior.year_id = tpu.trade_season - 1
        LEFT JOIN pitcher_perf p_prior2
            ON p_prior2.mlb_id = tpu.mlb_player_id
            AND p_prior2.year_id = tpu.trade_season - 2
        WHERE tpu.to_team_bref IS NOT NULL
        GROUP BY tpu.trade_event_id, tpu.to_team_bref, tpu.mlb_player_id,
                 h_prior.off_per_600, h_prior2.off_per_600,
                 p_prior.era_plus_dev, p_prior2.era_plus_dev
    )
    SELECT
        trade_event_id,
        receiver_bref,
        AVG(pre_trade_quality) AS receiver_acquired_player_quality,
        COUNT(pre_trade_quality) AS n_acquired_with_signal,
        COUNT(*) AS n_acquired_total
    FROM per_player_unified
    GROUP BY trade_event_id, receiver_bref
    """,
    """
    CREATE OR REPLACE VIEW trade_acquired_player_age_trajectory AS
    -- More within-team-variation features per D-24:
    --  - avg experience (years since first MLB season) of acquired players
    --  - avg WAR trajectory (war_t_minus_1 - war_t_minus_2) — improving vs declining
    -- Both vary across trades involving the same team, so they can claim
    -- residual variance against team-cluster intercepts.
    WITH first_season AS (
        SELECT mlb_id, MIN(year_id) AS first_year
        FROM bwar_player_seasons
        WHERE mlb_id IS NOT NULL
        GROUP BY mlb_id
    ),
    season_war AS (
        SELECT mlb_id, year_id, SUM(war) AS war
        FROM bwar_player_seasons
        WHERE mlb_id IS NOT NULL
        GROUP BY mlb_id, year_id
    ),
    per_player AS (
        SELECT
            tpu.trade_event_id,
            tpu.to_team_bref AS receiver_bref,
            (tpu.trade_season - fs.first_year) AS experience,
            (w1.war - w2.war) AS war_trajectory
        FROM trade_player_unified tpu
        LEFT JOIN first_season fs ON fs.mlb_id = tpu.mlb_player_id
        LEFT JOIN season_war w1
            ON w1.mlb_id = tpu.mlb_player_id AND w1.year_id = tpu.trade_season - 1
        LEFT JOIN season_war w2
            ON w2.mlb_id = tpu.mlb_player_id AND w2.year_id = tpu.trade_season - 2
        WHERE tpu.to_team_bref IS NOT NULL
    )
    SELECT
        trade_event_id,
        receiver_bref,
        AVG(experience) AS receiver_acquired_player_avg_experience,
        AVG(war_trajectory) AS receiver_acquired_player_avg_war_trajectory
    FROM per_player
    WHERE experience IS NOT NULL
    GROUP BY trade_event_id, receiver_bref
    """,
    """
    CREATE OR REPLACE VIEW trade_xwoba_outcome AS
    -- Rate-based aggregate outcome per (trade_event, receiver): mean Δ xwOBA
    -- of acquired hitters with Statcast data both pre- and post-trade.
    -- This is the non-WAR outcome variable for testing R-15's player-quality
    -- finding against a metric that isn't mechanically WAR-derivative (D-25).
    SELECT
        trade_event_id,
        to_team_bref AS receiver_bref,
        AVG(xwoba_t_plus_1 - xwoba_t_minus_1) AS xwoba_delta_mean,
        COUNT(*) AS n_hitters_with_signal
    FROM trade_player_xwoba_window
    WHERE xwoba_t_minus_1 IS NOT NULL
      AND xwoba_t_plus_1 IS NOT NULL
      AND to_team_bref IS NOT NULL
    GROUP BY trade_event_id, to_team_bref
    """,
    """
    CREATE OR REPLACE VIEW trade_origin_dev_cluster AS
    -- Per (trade_event, receiving_team), the average "dev-cluster" score of
    -- the origin teams the receiver acquired players from. R-12/13 found two
    -- camps among analytics-leader orgs:
    --   +1 = HOU, CLE: improvements installed travel with the departed player
    --   -1 = LAD, TBR, SDP, BOS: improvements don't travel; departures drop
    --    0 = everyone else
    -- A receiver who acquires players FROM the +1 cluster should expect those
    -- players to keep their improvement post-trade; from -1, expect dropoff.
    SELECT
        tpu.trade_event_id,
        tpu.to_team_bref AS receiver_bref,
        AVG(CASE
            WHEN tpu.from_team_bref IN ('HOU', 'CLE') THEN 1.0
            WHEN tpu.from_team_bref IN ('LAD', 'TBR', 'SDP', 'BOS') THEN -1.0
            ELSE 0.0
        END) AS receiver_acquired_from_dev_cluster_score,
        COUNT(*) AS n_acquired_players
    FROM trade_player_unified tpu
    WHERE tpu.to_team_bref IS NOT NULL
      AND tpu.from_team_bref IS NOT NULL
    GROUP BY tpu.trade_event_id, tpu.to_team_bref
    """,
    """
    CREATE OR REPLACE VIEW trade_pedigree AS
    -- Per (trade_event, receiving_team), aggregate draft-pick pedigree of
    -- players acquired. Lower pick_number = higher pedigree. Players without
    -- a matching draft record (international FAs, pre-1990 draftees) are
    -- dropped from the aggregate; n_with_pick tells you the coverage.
    SELECT
        tpu.trade_event_id,
        tpu.to_team_bref AS receiver_bref,
        MIN(d.pick_number) AS receiver_best_draft_pick,
        AVG(d.pick_number) AS receiver_avg_draft_pick,
        COUNT(d.pick_number) AS receiver_n_with_pick,
        COUNT(*) AS receiver_n_players
    FROM trade_player_unified tpu
    LEFT JOIN draft_picks d ON d.mlb_player_id = tpu.mlb_player_id
    WHERE tpu.to_team_bref IS NOT NULL
    GROUP BY tpu.trade_event_id, tpu.to_team_bref
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
        tsf.coach_hitter_xwoba_jump_3yr AS receiver_coach_hitter_xwoba_jump_3yr,
        tp.receiver_best_draft_pick,
        tp.receiver_avg_draft_pick,
        tdc.receiver_acquired_from_dev_cluster_score,
        pds.receiver_acquired_player_quality,
        pat.receiver_acquired_player_avg_experience,
        pat.receiver_acquired_player_avg_war_trajectory
    FROM naive_baseline_results nbr
    LEFT JOIN team_season_features tsf
        ON tsf.bref_code = nbr.team_bref
        AND tsf.season = nbr.trade_season
    LEFT JOIN trade_pedigree tp
        ON tp.trade_event_id = nbr.trade_event_id
        AND tp.receiver_bref = nbr.team_bref
    LEFT JOIN trade_origin_dev_cluster tdc
        ON tdc.trade_event_id = nbr.trade_event_id
        AND tdc.receiver_bref = nbr.team_bref
    LEFT JOIN trade_player_dev_signature pds
        ON pds.trade_event_id = nbr.trade_event_id
        AND pds.receiver_bref = nbr.team_bref
    LEFT JOIN trade_acquired_player_age_trajectory pat
        ON pat.trade_event_id = nbr.trade_event_id
        AND pat.receiver_bref = nbr.team_bref
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
