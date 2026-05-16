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
            team_season = team_season.merge(
                standings_df, on=["bref_code", "season"], how="left"
            )
        else:
            team_season["prior_year_wins"] = None
            team_season["prior_year_losses"] = None
            team_season["prior_year_pyth_pct"] = None

        team_season["prior_year_run_diff"] = None  # needs game-log adapter
        team_season["farm_war_top_10"] = None  # needs prospect FV (Phase 2.5)

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
            ]
        ]

        conn.register("_staging_tsf", rows)
        try:
            conn.execute(
                "INSERT INTO team_season_features "
                "(team_id, bref_code, season, prior_year_wins, prior_year_losses, "
                "prior_year_run_diff, prior_year_pyth_pct, prior_year_war, "
                "farm_war_top_10, org_dev_fit_pitching, org_dev_fit_hitting) "
                "SELECT team_id, bref_code, season, prior_year_wins, prior_year_losses, "
                "prior_year_run_diff, prior_year_pyth_pct, prior_year_war, "
                "farm_war_top_10, org_dev_fit_pitching, org_dev_fit_hitting "
                "FROM _staging_tsf"
            )
        finally:
            conn.unregister("_staging_tsf")

    n = int(rows.shape[0])
    logger.info("wrote %d team-season feature rows", n)
    return n
