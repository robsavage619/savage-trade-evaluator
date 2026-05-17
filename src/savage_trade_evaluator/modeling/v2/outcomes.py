"""V2 outcome variables.

Four outcome metrics per ``docs/V2_DESIGN.md`` — keyed on
(trade_event_id, receiver_bref) so they align with the feature matrix:

- ``xwoba_delta``: mean Δ xwOBA of acquired hitters with Statcast data
- ``kpct_delta``:  mean Δ K-percentile-rank of acquired pitchers
- ``war_delta``:   mean per-trade Δ WAR across acquired players (3yr cumul)
- ``dollar_surplus``: rate-based WAR × $/WAR − cap-hit obligations

Each is its own model fit per D-27 (feature importance is outcome-specific).
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db

# League $/WAR per season. Hardcoded for V2.0; could be derived from FA
# market signings in V2.1.
LEAGUE_DOLLAR_PER_WAR: dict[int, float] = {
    2010: 4_500_000,
    2011: 5_000_000,
    2012: 5_500_000,
    2013: 6_000_000,
    2014: 6_500_000,
    2015: 7_500_000,
    2016: 8_000_000,
    2017: 8_500_000,
    2018: 9_000_000,
    2019: 9_000_000,
    2020: 8_000_000,
    2021: 8_500_000,
    2022: 9_000_000,
    2023: 9_500_000,
    2024: 10_000_000,
}


def build_outcomes(start_season: int = 1990, end_season: int = 2024) -> pd.DataFrame:
    """Build the four-outcome target matrix.

    Returns a DataFrame keyed on (trade_event_id, receiver_bref) with columns:
    xwoba_delta, kpct_delta, war_delta, dollar_surplus.
    """
    values_clause = ", ".join(f"({y}, {v})" for y, v in LEAGUE_DOLLAR_PER_WAR.items())

    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            WITH r_recv AS (
                SELECT * FROM (VALUES {values_clause})
                AS t(season, dollar_per_war)
            ),
            base AS (
                SELECT trade_event_id, receiver_bref, trade_season,
                       surplus AS war_surplus,
                       war_received,
                       war_given_up
                FROM trade_with_context
                WHERE trade_season BETWEEN {start_season} AND {end_season}
            ),
            xwoba AS (
                SELECT trade_event_id, receiver_bref, xwoba_delta_mean AS xwoba_delta
                FROM trade_xwoba_outcome
            ),
            kpct AS (
                SELECT trade_event_id, receiver_bref, kpct_delta_mean AS kpct_delta
                FROM trade_kpct_outcome
            )
            SELECT b.trade_event_id, b.receiver_bref, b.trade_season,
                   x.xwoba_delta,
                   k.kpct_delta,
                   b.war_surplus AS war_delta,
                   -- Dollar surplus: receiver-side WAR × $/WAR − cap obligation
                   (b.war_received * COALESCE(r_recv.dollar_per_war, 8000000))
                       AS war_value_received_dollars,
                   (b.war_given_up * COALESCE(r_recv.dollar_per_war, 8000000))
                       AS war_value_given_up_dollars
            FROM base b
            LEFT JOIN xwoba x
                ON x.trade_event_id = b.trade_event_id
                AND x.receiver_bref = b.receiver_bref
            LEFT JOIN kpct k
                ON k.trade_event_id = b.trade_event_id
                AND k.receiver_bref = b.receiver_bref
            LEFT JOIN r_recv
                ON r_recv.season = b.trade_season
            """
        ).df()

    # Pull cap-hit obligations from Spotrac contracts for each (trade_event, receiver).
    # The receiver took on the cap_hit of players acquired; subtract it from the
    # WAR-value-received to get a real dollar surplus.
    with db.connect(read_only=True) as conn:
        cap = conn.execute(
            """
            SELECT tpu.trade_event_id, tpu.to_team_bref AS receiver_bref,
                   SUM(spc.cap_hit) AS total_cap_acquired
            FROM trade_player_unified tpu
            LEFT JOIN spotrac_player_contracts spc
                ON spc.mlb_player_id = tpu.mlb_player_id
                AND spc.season = tpu.trade_season
            WHERE tpu.to_team_bref IS NOT NULL
            GROUP BY tpu.trade_event_id, tpu.to_team_bref
            """
        ).df()
    df = df.merge(cap, on=["trade_event_id", "receiver_bref"], how="left")

    # Compute the final dollar surplus column. Skip the given-up side for V2.0
    # simplicity — that's an "other team's value out" calc that requires the
    # opposite-direction lookup; can layer in for V2.1.
    df["dollar_surplus"] = df["war_value_received_dollars"].fillna(0.0) - df[
        "total_cap_acquired"
    ].fillna(0.0)

    return df[
        [
            "trade_event_id",
            "receiver_bref",
            "trade_season",
            "xwoba_delta",
            "kpct_delta",
            "war_delta",
            "dollar_surplus",
        ]
    ]
