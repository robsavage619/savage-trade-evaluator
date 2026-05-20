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
    # Pedigree from mlb_awards (career awards strictly prior to trade season).
    "receiver_acquired_avg_prior_awards",
    "receiver_acquired_pct_awarded",
    # MiLB quality signals (from trade_acquired_milb_quality).
    "receiver_acquired_milb_hit_quality",
    "receiver_acquired_milb_pitch_quality",
    "receiver_acquired_milb_age_advantage",
    # Contract-year bias flag (approximated from bWAR salary coverage — see D-29).
    # Fraction of acquired players whose salary record ends at the trade season
    # (no salary entry for trade_season+1) and who have a non-null salary at
    # trade_season (rules out rookie-deal unknowns). Limitation: we don't have
    # Cot's Contracts; this is a proxy and will miss multi-year deals that happen
    # to have no next-season salary row due to data gaps.
    "receiver_acquired_contract_year_pct",
)

RECEIVER_TEAM_FEATURES: tuple[str, ...] = (
    "receiver_prior_year_war",
    "receiver_dev_fit_pitching",
    "receiver_dev_fit_hitting",
    "receiver_prior_year_pyth_pct",
    "receiver_org_pitcher_k_jump_3yr",
    "receiver_org_hitter_xwoba_jump_3yr",
    "receiver_total_payroll",
    # Contention window features (thesis core: payroll room × win probability).
    "receiver_payroll_pct_of_cap",
    "receiver_payroll_trend_3yr",
    "receiver_contention_window_score",
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
                -- Contention window features (thesis core)
                tspc.payroll_pct_of_cap AS receiver_payroll_pct_of_cap,
                tspc.payroll_trend_3yr  AS receiver_payroll_trend_3yr,
                -- Composite: high pyth_pct × low payroll commitment = win-now capacity
                twc.receiver_prior_year_pyth_pct
                    * GREATEST(0.0, 1.0 - COALESCE(tspc.payroll_pct_of_cap, 0.5))
                    AS receiver_contention_window_score,
                -- Origin features
                twc.receiver_acquired_from_dev_cluster_score,
                -- Pedigree (NEW from mlb_awards)
                tpp.avg_prior_awards AS receiver_acquired_avg_prior_awards,
                tpp.pct_awarded_players AS receiver_acquired_pct_awarded,
                -- MiLB quality (NEW from trade_acquired_milb_quality)
                tamq.receiver_acquired_milb_hit_quality,
                tamq.receiver_acquired_milb_pitch_quality,
                tamq.receiver_acquired_milb_age_advantage
            FROM trade_with_context twc
            LEFT JOIN trade_receiver_demographic_mix trdm
                ON trdm.trade_event_id = twc.trade_event_id
                AND trdm.receiver_bref = twc.receiver_bref
            LEFT JOIN spotrac_team_payroll stp
                ON stp.team_bref = twc.receiver_bref
                AND stp.season = twc.trade_season
            LEFT JOIN team_season_payroll_context tspc
                ON tspc.team_bref = twc.receiver_bref
                AND tspc.season   = twc.trade_season
            LEFT JOIN trade_acquired_player_pedigree tpp
                ON tpp.trade_event_id = twc.trade_event_id
                AND tpp.receiver_bref = twc.receiver_bref
            LEFT JOIN trade_acquired_milb_quality tamq
                ON tamq.trade_event_id = twc.trade_event_id
                AND tamq.receiver_bref = twc.receiver_bref
            LEFT JOIN (
                -- Contract-year bias flag: fraction of acquired players whose
                -- bWAR salary record covers the trade season but NOT the next
                -- season. Approximation only — Cot's Contracts not available.
                -- Join path: tpu.mlb_player_id → bwar_player_seasons.mlb_id.
                SELECT
                    tpu.trade_event_id,
                    tpu.to_team_bref AS receiver_bref,
                    SUM(CASE
                        WHEN has_salary_now = 1 AND has_salary_next = 0 THEN 1
                        ELSE 0
                    END)::DOUBLE / NULLIF(COUNT(*), 0)
                        AS receiver_acquired_contract_year_pct
                FROM trade_player_unified tpu
                LEFT JOIN (
                    SELECT mlb_id, year_id,
                        MAX(CASE WHEN salary IS NOT NULL THEN 1 ELSE 0 END) AS has_salary_now
                    FROM bwar_player_seasons
                    GROUP BY mlb_id, year_id
                ) bps_now
                    ON bps_now.mlb_id = tpu.mlb_player_id
                    AND bps_now.year_id = tpu.trade_season
                LEFT JOIN (
                    SELECT mlb_id, year_id,
                        MAX(CASE WHEN salary IS NOT NULL THEN 1 ELSE 0 END) AS has_salary_next
                    FROM bwar_player_seasons
                    GROUP BY mlb_id, year_id
                ) bps_next
                    ON bps_next.mlb_id = tpu.mlb_player_id
                    AND bps_next.year_id = tpu.trade_season + 1
                WHERE tpu.to_team_bref IS NOT NULL
                GROUP BY tpu.trade_event_id, tpu.to_team_bref
            ) cy
                ON cy.trade_event_id = twc.trade_event_id
                AND cy.receiver_bref  = twc.receiver_bref
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
