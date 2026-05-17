"""V2 feature pipeline.

Assembles the three-bucket feature matrix per ``docs/V2_DESIGN.md``:

1. Acquired-player features (within-trade variation per D-24)
2. Receiver-team context (per team-season)
3. Origin-side features (per origin team-season; derivative)

Returns a single DataFrame keyed on (trade_event_id, receiver_bref) ready
to feed into the multilevel fit.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.modeling.v2.regimes import attach_regime_id
from savage_trade_evaluator.storage import db

# V2 feature columns, three buckets. All from existing views.
ACQUIRED_PLAYER_FEATURES: tuple[str, ...] = (
    "receiver_acquired_player_quality",
    "receiver_acquired_player_avg_war_trajectory",
    "receiver_acquired_pitcher_k_trajectory",
    "receiver_acquired_pitcher_arsenal_volatility",
    "receiver_avg_age_at_trade",
    "receiver_pct_international_born",
    "receiver_pct_left_handed_bat",
    "receiver_pct_pitchers",
)

RECEIVER_TEAM_FEATURES: tuple[str, ...] = (
    "receiver_prior_year_war",
    "receiver_dev_fit_pitching",
    "receiver_dev_fit_hitting",
    "receiver_prior_year_pyth_pct",
    "receiver_org_pitcher_k_jump_3yr",
    "receiver_org_hitter_xwoba_jump_3yr",
    "receiver_total_payroll",
)

ORIGIN_FEATURES: tuple[str, ...] = ("receiver_acquired_from_dev_cluster_score",)

ALL_FEATURES: tuple[str, ...] = ACQUIRED_PLAYER_FEATURES + RECEIVER_TEAM_FEATURES + ORIGIN_FEATURES


def build_feature_matrix(start_season: int = 1990, end_season: int = 2024) -> pd.DataFrame:
    """Assemble the V2 feature matrix from existing views.

    Returns a DataFrame with one row per (trade_event_id, receiver_bref),
    every column in ALL_FEATURES plus ``regime_id`` for cluster lookup.
    """
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT
                twc.trade_event_id,
                twc.trade_season,
                twc.receiver_bref,
                -- Acquired-player features (from trade_with_context)
                twc.receiver_acquired_player_quality,
                twc.receiver_acquired_player_avg_war_trajectory,
                twc.receiver_acquired_pitcher_k_trajectory,
                twc.receiver_acquired_pitcher_arsenal_volatility,
                -- Demographic mix (from trade_receiver_demographic_mix)
                trdm.avg_age_at_trade AS receiver_avg_age_at_trade,
                trdm.pct_international_born AS receiver_pct_international_born,
                trdm.pct_left_handed_bat AS receiver_pct_left_handed_bat,
                trdm.pct_pitchers AS receiver_pct_pitchers,
                -- Receiver-team context (from trade_with_context)
                twc.receiver_prior_year_war,
                twc.receiver_dev_fit_pitching,
                twc.receiver_dev_fit_hitting,
                twc.receiver_prior_year_pyth_pct,
                twc.receiver_org_pitcher_k_jump_3yr,
                twc.receiver_org_hitter_xwoba_jump_3yr,
                -- Payroll context (NEW from Spotrac)
                stp.total_payroll AS receiver_total_payroll,
                -- Origin features
                twc.receiver_acquired_from_dev_cluster_score
            FROM trade_with_context twc
            LEFT JOIN trade_receiver_demographic_mix trdm
                ON trdm.trade_event_id = twc.trade_event_id
                AND trdm.receiver_bref = twc.receiver_bref
            LEFT JOIN spotrac_team_payroll stp
                ON stp.team_bref = twc.receiver_bref
                AND stp.season = twc.trade_season
            WHERE twc.trade_season BETWEEN {start_season} AND {end_season}
            """
        ).df()

    df = attach_regime_id(df)
    return df


def filter_complete_cases(
    df: pd.DataFrame, required_cols: tuple[str, ...] | None = None
) -> pd.DataFrame:
    """Drop rows missing any required feature.

    Required cols default to ALL_FEATURES. Pass a subset to allow partial
    coverage (e.g. early seasons where Spotrac payroll is unavailable).
    """
    cols = list(required_cols or ALL_FEATURES)
    return df.dropna(subset=cols).reset_index(drop=True)
