"""40-man roster mechanics: IL history, options usage, and crunch analysis.

Data is derived entirely from the existing ``transactions`` table via the
``il_stints`` and ``player_option_years`` views (see storage/trade_views.py).
No new ingestion required.

Limitations (V1 approximation):
  - IL stint pairing matches the N-th placement to the N-th activation per player
    in date order. Players still on the IL at query time will have NULL activation.
  - Options-used counts are approximated from 'Optioned' transaction rows.
    Players who exhausted options before 2010 (transactions coverage start) will
    be under-counted.
  - Rule 5 eligibility uses the draft-year heuristic: eligible after 4 or 5
    professional seasons depending on signing age. International signings are
    tracked with the same heuristic since international signing dates are not
    reliably ingested.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# MLB rule: players drafted at 19+ have 4 professional seasons before Rule 5 exposure;
# players signed at 18 or younger have 5 seasons. We approximate with 4 for everyone —
# errs toward over-flagging exposure, which is the safer direction for a GM tool.
_RULE5_SEASONS_TO_EXPOSURE = 4


def forty_man_report(team: str, season: int) -> pd.DataFrame:
    """Build a 40-man crunch report for a team-season.

    Returns one row per 40-man roster player with:
      - player_id, player_name, position
      - options_used: approximate number of option seasons 2010+
      - il_stints_career: IL placements on record (2010+)
      - draft_year: year drafted (or None if undrafted/international)
      - seasons_pro: estimated professional seasons (season - draft_year)
      - rule5_exposed: True if seasons_pro >= _RULE5_SEASONS_TO_EXPOSURE
      - surplus_war: prior-season WAR (proxy for roster value)
      - crunch_flag: 'out_of_options' | 'rule5_risk' | 'il_burden' | 'ok'

    Args:
        team: Baseball Reference team code (e.g. 'SEA', 'HOU').
        season: Season of interest.

    Returns:
        DataFrame sorted by crunch_flag severity, then by surplus_war ascending
        (lowest-value players with flags first — the decision candidates).
    """
    team = team.upper()

    with db.connect(read_only=True) as conn:
        # 40-man snapshot
        roster_df = conn.execute(
            """
            SELECT
                r.player_id,
                COALESCE(mp.full_name, r.player_name) AS player_name,
                r.position_name AS position
            FROM team_rosters r
            LEFT JOIN mlb_people mp ON mp.mlb_player_id = r.player_id
            WHERE r.team_id = ? AND r.season = ? AND r.roster_type = '40Man'
              AND r.player_id IS NOT NULL
            """,
            [team, season],
        ).fetchdf()

        if roster_df.empty:
            logger.warning("no 40-man roster found for %s/%d", team, season)
            return roster_df

        player_ids = roster_df["player_id"].tolist()
        ids_placeholder = ",".join("?" * len(player_ids))

        # Options used (2010+)
        options_df = conn.execute(
            f"""
            SELECT player_id, COUNT(DISTINCT season) AS options_used
            FROM transactions
            WHERE type_desc = 'Optioned' AND player_id IN ({ids_placeholder})
            GROUP BY player_id
            """,
            player_ids,
        ).fetchdf()

        # IL stints (2010+)
        il_df = conn.execute(
            f"""
            SELECT player_id, COUNT(*) AS il_stints_career
            FROM il_stints
            WHERE player_id IN ({ids_placeholder})
            GROUP BY player_id
            """,
            player_ids,
        ).fetchdf()

        # Prior-season WAR
        war_df = conn.execute(
            f"""
            SELECT
                COALESCE(b.mlb_id, p.mlb_id) AS player_id,
                COALESCE(b.war, 0.0) + COALESCE(p.war, 0.0) AS surplus_war
            FROM (
                SELECT mlb_id, SUM(war) AS war
                FROM bwar_batting
                WHERE year_id = ? AND mlb_id IN ({ids_placeholder})
                GROUP BY mlb_id
            ) b
            FULL OUTER JOIN (
                SELECT mlb_id, SUM(war) AS war
                FROM bwar_pitching
                WHERE year_id = ? AND mlb_id IN ({ids_placeholder})
                GROUP BY mlb_id
            ) p ON p.mlb_id = b.mlb_id
            """,
            [season - 1, *player_ids, season - 1, *player_ids],
        ).fetchdf()

        # Draft year from draft_picks
        draft_year_df = conn.execute(
            f"""
            SELECT DISTINCT ON (mlb_player_id) mlb_player_id AS player_id,
                   draft_year
            FROM draft_picks dp
            JOIN chadwick_register cr ON cr.retro_id = dp.player_retro_id
               OR cr.mlb_player_id = dp.player_mlb_id
            WHERE cr.mlb_player_id IN ({ids_placeholder})
            """,
            player_ids,
        ).fetchdf()

    df = roster_df.merge(options_df, on="player_id", how="left")
    df = df.merge(il_df, on="player_id", how="left")
    df = df.merge(draft_year_df, on="player_id", how="left")
    df = df.merge(war_df, on="player_id", how="left")

    df["options_used"] = df["options_used"].fillna(0).astype(int)
    df["il_stints_career"] = df["il_stints_career"].fillna(0).astype(int)
    df["surplus_war"] = df["surplus_war"].fillna(0.0)

    df["seasons_pro"] = season - df["draft_year"].fillna(season)
    df["rule5_exposed"] = df["seasons_pro"] >= _RULE5_SEASONS_TO_EXPOSURE

    df["crunch_flag"] = np.select(
        condlist=[
            df["options_used"] >= 3,
            df["rule5_exposed"] & (df["surplus_war"] < 1.0),
            (df["il_stints_career"] >= 3) & (df["surplus_war"] < 0.5),
        ],
        choicelist=["out_of_options", "rule5_risk", "il_burden"],
        default="ok",
    )

    flag_order = {"out_of_options": 0, "rule5_risk": 1, "il_burden": 2, "ok": 3}
    df["_flag_ord"] = df["crunch_flag"].apply(lambda x: flag_order.get(str(x), 3))
    df = df.sort_values(["_flag_ord", "surplus_war"], ascending=[True, True])
    df = df.drop(columns=["_flag_ord", "seasons_pro"])

    logger.info(
        "40-man report for %s/%d: %d players, %d flagged",
        team,
        season,
        len(df),
        (df["crunch_flag"] != "ok").sum(),
    )
    return df.reset_index(drop=True)
