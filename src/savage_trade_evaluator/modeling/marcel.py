"""B1: Marcel-style expected WAR baseline for trade residual outcome.

Computes a deterministic ``expected_war_delta`` for each traded player using:
  1. 3:2:1 weighted average of last 3 seasons WAR (Marcel weighting)
  2. Linear aging-curve adjustment (Tango's simplified curve)

The residual outcome is:
  war_delta_residual = war_delta - expected_war_delta

This removes the "player was going to age/decline anyway" component and
isolates the value attributable to the receiving team's development context —
which is exactly the variation the thesis (D-01) claims to predict.

**Status: pre-production.** Gated on go/no-go from D-49 (to be filed after
initial experimental results). ``war_delta_residual`` is added to
``assemble_v3_combined()`` as a supplementary column only — it does not
replace ``war_delta`` without an explicit decision.
"""

from __future__ import annotations

import logging

import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

# Tango's simplified aging curve (per year deviation from career mean).
# Players improve before PEAK_AGE, decline after.
# Values from Marcel Projection System documentation / Tom Tango's work.
PEAK_AGE: int = 27
IMPROVEMENT_RATE: float = 0.3   # WAR/yr gain before peak (positive)
DECLINE_RATE: float = 0.3       # WAR/yr loss after peak (positive, applied as loss)

# Marcel 3:2:1 recency weights for T-1, T-2, T-3 seasons.
MARCEL_WEIGHTS: tuple[float, float, float] = (3.0, 2.0, 1.0)

# Regression-to-mean weight: Marcel blends historical with league-average replacement
# (typically ~0.2 WAR for a full-season player). We use a light blend.
REGRESSION_WEIGHT: float = 1.0   # light regression toward replacement level
REPLACEMENT_WAR: float = 0.2     # league-average WAR per 600 PA (full season proxy)


def _age_adjustment(age_at_trade: float, year_offset: int) -> float:
    """Age-curve WAR delta for a given year relative to trade season.

    Args:
        age_at_trade: Player's age during the trade season (at T-0).
        year_offset: Offset from trade season (1 = T+1, 2 = T+2, ...).

    Returns:
        Expected WAR contribution from aging alone for that year.
    """
    age = age_at_trade + year_offset
    if age < PEAK_AGE:
        return IMPROVEMENT_RATE
    return -DECLINE_RATE


def _marcel_projection(
    war_t1: float | None,
    war_t2: float | None,
    war_t3: float | None,
) -> float:
    """Marcel single-season WAR projection.

    Args:
        war_t1: WAR in T-1 (most recent season before trade). May be None if missing.
        war_t2: WAR in T-2. May be None.
        war_t3: WAR in T-3. May be None.

    Returns:
        Marcel projected WAR for T+1.
    """
    vals = [v for v in [war_t1, war_t2, war_t3] if v is not None]
    wts  = list(MARCEL_WEIGHTS[: len(vals)])

    if not vals:
        # No prior data — fall back to replacement level
        return REPLACEMENT_WAR

    weighted_avg = sum(v * w for v, w in zip(vals, wts, strict=False)) / sum(wts)
    # Regression to mean: blend with REPLACEMENT_WAR over (sum_wts + REGRESSION_WEIGHT)
    blended = (weighted_avg * sum(wts) + REPLACEMENT_WAR * REGRESSION_WEIGHT) / (
        sum(wts) + REGRESSION_WEIGHT
    )
    return blended


def expected_war_delta(
    war_t1: float | None,
    war_t2: float | None,
    war_t3: float | None,
    age_at_trade: float,
    window_start: int = 2,
    window_end: int = 5,
) -> float:
    """Expected WAR delta over a post-trade window using Marcel + aging curve.

    Args:
        war_t1: Player's WAR in the season immediately before the trade (T-1).
        war_t2: Player's WAR two seasons before the trade (T-2).
        war_t3: Player's WAR three seasons before the trade (T-3).
        age_at_trade: Player's age during the trade season (T-0).
        window_start: First year of the outcome window (e.g., 2 for T+2..T+5).
        window_end: Last year (inclusive) of the outcome window.

    Returns:
        Expected WAR delta (T+window_start..T+window_end sum) minus WAR in T-1.
        Comparable to ``war_delta`` from the V3 default outcome window.
    """
    base_war = _marcel_projection(war_t1, war_t2, war_t3)

    # Project year-by-year, applying cumulative aging adjustments.
    # Each year's projection starts from the prior year's base_war (simplified:
    # we hold the non-aging component constant and only apply the age curve).
    total_expected = 0.0
    for offset in range(window_start, window_end + 1):
        age_adj = sum(_age_adjustment(age_at_trade, k) for k in range(1, offset + 1))
        expected_year = base_war + age_adj
        total_expected += expected_year

    war_t1_anchor = war_t1 if war_t1 is not None else REPLACEMENT_WAR
    return total_expected - war_t1_anchor


def build_marcel_residuals(
    war_window_start: int = 2,
    war_window_end: int = 5,
) -> pd.DataFrame:
    """Compute Marcel expected_war_delta and war_delta_residual for all trade events.

    Joins bWAR data (T-1, T-2, T-3) with chadwick birth_year, then calls
    ``expected_war_delta()`` per row.

    Args:
        war_window_start: Start of the war_delta window (default 2 → T+2).
        war_window_end: End of the war_delta window (default 5 → T+5).

    Returns:
        DataFrame keyed on (trade_event_id, receiver_bref, trade_season) with:
        - ``expected_war_delta``: Marcel projected delta over the window.
        - ``war_delta_residual``: ``war_delta - expected_war_delta`` (only where
          war_delta is not null; else null).
    """
    with db.connect(read_only=True) as conn:
        # receiver_bref here is the RECEIVING TEAM's bref ID (e.g. "HOU"), not the player.
        # This matches the assemble_combined() key: (trade_event_id, receiver_bref, trade_season).
        df = conn.execute(
            """
            WITH bwar_annual AS (
                -- Sum all stints so each player has one WAR row per season.
                -- Combine batting + pitching (two-way players appear in both tables).
                SELECT mlb_id, year_id, SUM(war) AS war
                FROM (
                    SELECT mlb_id, year_id, war FROM bwar_batting
                    UNION ALL
                    SELECT mlb_id, year_id, war FROM bwar_pitching
                ) all_war
                GROUP BY mlb_id, year_id
            ),
            player_age AS (
                SELECT mlb_player_id, birth_year
                FROM chadwick_register
                WHERE birth_year IS NOT NULL
            ),
            -- Deduplicate: one row per (trade_event_id, to_team_bref, mlb_player_id).
            -- Multi-leg stints can produce duplicate mlb_player_id rows for the same
            -- receiving team (e.g. Scherzer in the LAD-WSN trade has two leg_index values).
            distinct_players AS (
                SELECT DISTINCT trade_event_id, trade_season, to_team_bref, mlb_player_id
                FROM trade_player_unified
                WHERE mlb_player_id IS NOT NULL
            ),
            trade_base AS (
                SELECT
                    dp.trade_event_id,
                    dp.trade_season,
                    dp.to_team_bref       AS receiver_bref,
                    dp.mlb_player_id,
                    pa.birth_year,
                    b1.war AS war_tm1,
                    b2.war AS war_tm2,
                    b3.war AS war_tm3
                FROM distinct_players dp
                LEFT JOIN player_age pa ON pa.mlb_player_id = dp.mlb_player_id
                LEFT JOIN bwar_annual b1
                    ON b1.mlb_id = dp.mlb_player_id
                    AND b1.year_id = dp.trade_season - 1
                LEFT JOIN bwar_annual b2
                    ON b2.mlb_id = dp.mlb_player_id
                    AND b2.year_id = dp.trade_season - 2
                LEFT JOIN bwar_annual b3
                    ON b3.mlb_id = dp.mlb_player_id
                    AND b3.year_id = dp.trade_season - 3
            )
            SELECT
                trade_event_id,
                trade_season,
                receiver_bref,
                mlb_player_id,
                birth_year,
                war_tm1,
                war_tm2,
                war_tm3
            FROM trade_base
            """
        ).df()

    logger.info("build_marcel_residuals: %d rows loaded", len(df))

    df["age_at_trade"] = df["trade_season"] - df["birth_year"].astype("Float64")

    def _row_expected(row: pd.Series) -> float:
        age = float(row["age_at_trade"]) if not pd.isna(row["age_at_trade"]) else 28.0
        return expected_war_delta(
            war_t1=row["war_tm1"] if not pd.isna(row["war_tm1"]) else None,
            war_t2=row["war_tm2"] if not pd.isna(row["war_tm2"]) else None,
            war_t3=row["war_tm3"] if not pd.isna(row["war_tm3"]) else None,
            age_at_trade=age,
            window_start=war_window_start,
            window_end=war_window_end,
        )

    df["expected_war_delta_player"] = df.apply(_row_expected, axis=1)

    # Aggregate per-player estimates to the (trade_event_id, receiver_bref, trade_season) level.
    # war_delta in assemble_combined() is already the SUM across all players going to the receiver
    # team, so expected should also be the SUM.
    agg = (
        df.groupby(["trade_event_id", "receiver_bref", "trade_season"], as_index=False)[
            "expected_war_delta_player"
        ]
        .sum()
        .rename(columns={"expected_war_delta_player": "expected_war_delta"})
    )
    logger.info("build_marcel_residuals: aggregated to %d (trade, team, season) rows", len(agg))
    return agg
