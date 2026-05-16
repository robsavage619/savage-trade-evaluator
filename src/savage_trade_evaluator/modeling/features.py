"""Team-season feature engineering for the context-aware model.

Builds per-(team, season) features that the V2 model conditions on. Sources:

* **Contention window proxy**: prior-season W-L and Pythagorean expectation
  (run differential / total runs squared). Derived from bWAR aggregates since
  we don't have standings ingested separately.
* **Org-level dev-fit**: minor-league system performance — for V0 we proxy
  with the team's same-season aggregated bWAR (positive = system producing).
* **Pitching vs hitting dev-fit decomposed**: separate aggregates for
  pitcher and batter sides of the team-season bWAR sum.

This is *not* the full feature set from the planning brief (no playoff-odds,
no payroll-room, no manager dev-track-record yet — those need additional
data sources). This is the V1 feature set the data layer already supports.
"""

# pyright: reportCallIssue=false, reportAttributeAccessIssue=false, reportArgumentType=false

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def compute_all() -> int:
    """Compute team-season features for every (team, season) and persist.

    Idempotent — wipes the table and recomputes from current source data.

    Returns:
        Number of rows written.
    """
    with db.connect() as conn:
        schemas.initialize(conn)

        # Aggregate bWAR by team-season for both batting and pitching sides.
        # Use the canonical teams table to translate bref codes to MLB IDs.
        conn.execute("DELETE FROM team_season_features")

        # Pull team-season aggregates as a working set.
        team_season = conn.execute(
            """
            WITH bat AS (
                SELECT team_id AS bref_code, year_id AS season,
                       SUM(war) AS bat_war
                FROM bwar_batting
                WHERE team_id IS NOT NULL
                GROUP BY team_id, year_id
            ),
            pit AS (
                SELECT team_id AS bref_code, year_id AS season,
                       SUM(war) AS pit_war
                FROM bwar_pitching
                WHERE team_id IS NOT NULL
                GROUP BY team_id, year_id
            )
            SELECT t.mlb_team_id AS team_id,
                   t.bref_code,
                   COALESCE(bat.season, pit.season) AS season,
                   COALESCE(bat.bat_war, 0) AS bat_war,
                   COALESCE(pit.pit_war, 0) AS pit_war,
                   COALESCE(bat.bat_war, 0) + COALESCE(pit.pit_war, 0) AS total_war
            FROM teams t
            LEFT JOIN bat ON bat.bref_code = t.bref_code
            LEFT JOIN pit ON pit.bref_code = t.bref_code AND pit.season = bat.season
            WHERE COALESCE(bat.season, pit.season) IS NOT NULL
            """
        ).df()

        if team_season.empty:
            logger.warning("no team-season aggregates found")
            return 0

        # Construct prior-year features by shifting one season per team.
        team_season = team_season.sort_values(["bref_code", "season"]).reset_index(drop=True)
        team_season["prior_year_war"] = team_season.groupby("bref_code")["total_war"].shift(1)
        team_season["org_dev_fit_hitting"] = team_season["bat_war"]
        team_season["org_dev_fit_pitching"] = team_season["pit_war"]

        # Pull standings → join prior-year W-L by (team, season-1).
        standings_df = conn.execute(
            "SELECT bref_code, season, wins, losses, win_pct FROM standings"
        ).df()
        if not standings_df.empty:
            standings_df = standings_df.rename(
                columns={"wins": "prior_year_wins", "losses": "prior_year_losses"}
            )
            standings_df["season"] = standings_df["season"] + 1  # shift to "prior year"
            standings_df["prior_year_pyth_pct"] = standings_df["win_pct"]
            standings_df = standings_df.drop(columns=["win_pct"])
            team_season = team_season.merge(standings_df, on=["bref_code", "season"], how="left")
        else:
            team_season["prior_year_wins"] = None
            team_season["prior_year_losses"] = None
            team_season["prior_year_pyth_pct"] = None

        team_season["prior_year_run_diff"] = None  # needs game-log adapter
        team_season["farm_war_top_10"] = None  # needs prospect FV (Phase 2.5)

        # === MVP Machine Ch 9 thesis: per-team historical K-jump on acquired pitchers ===
        # For each (team t, season s), avg of (k_percent_t_plus_1 - k_percent_t_minus_1)
        # for every pitcher this team acquired in seasons [s-3, s-1]. Proxies
        # "this team's coaching staff systematically improves acquired pitchers."
        dev_history = conn.execute(
            """
            SELECT to_team_bref AS bref_code,
                   trade_season,
                   AVG(k_percent_t_plus_1 - k_percent_t_minus_1) AS k_jump_avg,
                   COUNT(*) AS n_pitchers
            FROM trade_player_arsenal_window
            WHERE k_percent_t_minus_1 IS NOT NULL
              AND k_percent_t_plus_1 IS NOT NULL
              AND to_team_bref IS NOT NULL
            GROUP BY to_team_bref, trade_season
            """
        ).df()
        if not dev_history.empty:
            # rolling 3-year mean per team
            dev_history = dev_history.sort_values(["bref_code", "trade_season"])
            dev_history["k_jump_3yr"] = (
                dev_history.groupby("bref_code")["k_jump_avg"]
                .rolling(window=3, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
            )
            # shift forward so feature is "what we knew BEFORE this season"
            dev_history["season"] = dev_history["trade_season"] + 1
            dev_history = dev_history[["bref_code", "season", "k_jump_3yr"]].rename(
                columns={"k_jump_3yr": "org_pitcher_k_jump_3yr"}
            )
            team_season = team_season.merge(dev_history, on=["bref_code", "season"], how="left")
        else:
            team_season["org_pitcher_k_jump_3yr"] = None

        # === MVP Machine Ch 5 thesis: per-team historical xwOBA-jump on acquired hitters ===
        # Hitting-side analog. For each (team t, season s), avg of
        # (xwoba_t_plus_1 - xwoba_t_minus_1) for every hitter this team acquired
        # in seasons [s-3, s-1]. Proxies "this team's hitting coaching staff
        # systematically improves acquired hitters' quality-of-contact" — the
        # Latta / Hyers story for Turner / Betts.
        hit_history = conn.execute(
            """
            SELECT to_team_bref AS bref_code,
                   trade_season,
                   AVG(xwoba_t_plus_1 - xwoba_t_minus_1) AS xwoba_jump_avg,
                   COUNT(*) AS n_hitters
            FROM trade_player_xwoba_window
            WHERE xwoba_t_minus_1 IS NOT NULL
              AND xwoba_t_plus_1 IS NOT NULL
              AND to_team_bref IS NOT NULL
            GROUP BY to_team_bref, trade_season
            """
        ).df()
        if not hit_history.empty:
            hit_history = hit_history.sort_values(["bref_code", "trade_season"])
            hit_history["xwoba_jump_3yr"] = (
                hit_history.groupby("bref_code")["xwoba_jump_avg"]
                .rolling(window=3, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
            )
            hit_history["season"] = hit_history["trade_season"] + 1
            hit_history = hit_history[["bref_code", "season", "xwoba_jump_3yr"]].rename(
                columns={"xwoba_jump_3yr": "org_hitter_xwoba_jump_3yr"}
            )
            team_season = team_season.merge(hit_history, on=["bref_code", "season"], how="left")
        else:
            team_season["org_hitter_xwoba_jump_3yr"] = None

        # === MVP Machine Ch 5 thesis — per-coach version (R-07) ===
        # The team-aggregate hitter feature was ~zero contribution (R-06 ablation).
        # Hypothesis: hitting dev-fit lives at the per-coach level, not per-team.
        # When Tim Hyers moved LAD-asst → BOS-head → TEX-head, his coaching
        # signal moved with him; a team-aggregate diluted across staff turnover.
        #
        # Feature: for each (team t, season s), find the hitting coach (COAT)
        # in place at season s-1, then compute that coach's trailing-3yr mean
        # of (xwoba_t_plus_1 - xwoba_t_minus_1) for hitters acquired during their
        # tenure ANYWHERE (across teams they've coached).
        coach_assignments = conn.execute(
            """
            SELECT c.team_id, t.bref_code, c.season, c.person_name
            FROM coaches c
            JOIN teams t ON t.mlb_team_id = c.team_id
            WHERE c.job_code = 'COAT' AND c.person_name IS NOT NULL
            """
        ).df()

        # per-trade xwoba jump joined to the receiving team's COAT at trade-season
        hitter_trades = conn.execute(
            """
            SELECT w.to_team_bref AS bref_code, w.trade_season,
                   w.xwoba_t_plus_1 - w.xwoba_t_minus_1 AS xwoba_jump,
                   c.person_name AS coach_name
            FROM trade_player_xwoba_window w
            JOIN teams t ON t.bref_code = w.to_team_bref
            JOIN coaches c ON c.team_id = t.mlb_team_id
                          AND c.season = w.trade_season
                          AND c.job_code = 'COAT'
            WHERE w.xwoba_t_minus_1 IS NOT NULL
              AND w.xwoba_t_plus_1 IS NOT NULL
            """
        ).df()

        if not hitter_trades.empty:
            # per-(coach, trade_season): mean xwoba_jump
            coach_season = (
                hitter_trades.groupby(["coach_name", "trade_season"])
                .agg(coach_xwoba_jump=("xwoba_jump", "mean"))
                .reset_index()
                .sort_values(["coach_name", "trade_season"])
            )
            # trailing 3-year rolling mean per coach (across teams they've coached)
            coach_season["coach_xwoba_jump_3yr"] = (
                coach_season.groupby("coach_name")["coach_xwoba_jump"]
                .rolling(window=3, min_periods=1)
                .mean()
                .reset_index(level=0, drop=True)
            )
            # shift forward — feature represents pre-trade-year knowledge
            coach_season["season"] = coach_season["trade_season"] + 1
            coach_record = coach_season[["coach_name", "season", "coach_xwoba_jump_3yr"]]

            # join coach assignments (which team a coach was at in season s) to
            # their trailing-3yr record from prior seasons
            coach_at_team = (
                coach_assignments.rename(columns={"person_name": "coach_name"}).merge(
                    coach_record, on=["coach_name", "season"], how="left"
                )
            )[["bref_code", "season", "coach_xwoba_jump_3yr"]].rename(
                columns={"coach_xwoba_jump_3yr": "coach_hitter_xwoba_jump_3yr"}
            )

            # in rare interim-coach swaps a team has 2+ COAT rows in a season —
            # keep the one with non-null record
            coach_at_team = coach_at_team.sort_values(
                "coach_hitter_xwoba_jump_3yr", na_position="last"
            ).drop_duplicates(["bref_code", "season"], keep="first")

            team_season = team_season.merge(coach_at_team, on=["bref_code", "season"], how="left")
        else:
            team_season["coach_hitter_xwoba_jump_3yr"] = None

        rows = team_season[
            [
                "team_id",
                "bref_code",
                "season",
                "prior_year_wins",
                "prior_year_losses",
                "prior_year_run_diff",
                "prior_year_pyth_pct",
                "prior_year_war",
                "farm_war_top_10",
                "org_dev_fit_pitching",
                "org_dev_fit_hitting",
                "org_pitcher_k_jump_3yr",
                "org_hitter_xwoba_jump_3yr",
                "coach_hitter_xwoba_jump_3yr",
            ]
        ]

        conn.register("_staging_tsf", rows)
        try:
            conn.execute(
                "INSERT INTO team_season_features "
                "(team_id, bref_code, season, prior_year_wins, prior_year_losses, "
                "prior_year_run_diff, prior_year_pyth_pct, prior_year_war, "
                "farm_war_top_10, org_dev_fit_pitching, org_dev_fit_hitting, "
                "org_pitcher_k_jump_3yr, org_hitter_xwoba_jump_3yr, "
                "coach_hitter_xwoba_jump_3yr) "
                "SELECT team_id, bref_code, season, prior_year_wins, prior_year_losses, "
                "prior_year_run_diff, prior_year_pyth_pct, prior_year_war, "
                "farm_war_top_10, org_dev_fit_pitching, org_dev_fit_hitting, "
                "org_pitcher_k_jump_3yr, org_hitter_xwoba_jump_3yr, "
                "coach_hitter_xwoba_jump_3yr "
                "FROM _staging_tsf"
            )
        finally:
            conn.unregister("_staging_tsf")

    n = int(rows.shape[0])
    logger.info("wrote %d team-season feature rows", n)
    return n
