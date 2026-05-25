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

# Hand-curated league $/WAR per season. Fallback only — preferred path is
# the empirical curve from compute_empirical_dollar_per_war() below, which
# is derived from Spotrac veteran-cohort cap_hit / cohort bWAR.
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


_DOLLAR_PER_WAR_CACHE: dict[int, float] | None = None


def compute_empirical_dollar_per_war() -> dict[int, float]:
    """Derive $/WAR per season empirically from Spotrac veteran contracts.

    Veterans (status='Veteran') are post-arbitration / open-market players,
    the cleanest proxy for FA-market pricing within the data we have. For
    each season: cohort cap_hit summed / cohort positive-WAR summed.

    Falls back to ``LEAGUE_DOLLAR_PER_WAR`` for any season the query
    cannot compute (notably 2010 — Spotrac coverage starts 2011).

    Result is cached at module level; call ``reset_dollar_per_war_cache()``
    to force recompute (used by tests / ablations).
    """
    global _DOLLAR_PER_WAR_CACHE  # noqa: PLW0603
    if _DOLLAR_PER_WAR_CACHE is not None:
        return _DOLLAR_PER_WAR_CACHE

    with db.connect(read_only=True) as conn:
        rows = conn.execute(
            """
            WITH vet AS (
                SELECT season, mlb_player_id, cap_hit
                FROM spotrac_player_contracts
                WHERE status = 'Veteran' AND cap_hit IS NOT NULL
            ),
            war AS (
                SELECT year_id AS season,
                       mlb_id AS mlb_player_id,
                       GREATEST(SUM(COALESCE(war, 0)), 0.0) AS pos_war
                FROM bwar_player_seasons
                GROUP BY year_id, mlb_id
            )
            SELECT v.season,
                   SUM(v.cap_hit) AS total_cap,
                   SUM(w.pos_war) AS total_war
            FROM vet v
            LEFT JOIN war w
                ON w.season = v.season AND w.mlb_player_id = v.mlb_player_id
            GROUP BY v.season
            HAVING SUM(w.pos_war) > 50
            ORDER BY v.season
            """
        ).fetchall()

    empirical = {int(s): float(cap) / float(war) for s, cap, war in rows}
    # Fill any missing season from the hand-curated fallback.
    out = {**LEAGUE_DOLLAR_PER_WAR, **empirical}
    _DOLLAR_PER_WAR_CACHE = out
    return out


def reset_dollar_per_war_cache() -> None:
    """Clear the module-level cache (for tests / ablations)."""
    global _DOLLAR_PER_WAR_CACHE  # noqa: PLW0603
    _DOLLAR_PER_WAR_CACHE = None


def build_outcomes_windowed(
    start_season: int = 1990,
    end_season: int = 2024,
    war_window_start: int = 1,
    war_window_end: int = 3,
) -> pd.DataFrame:
    """Parameterised outcome builder for Q-02/Q-07 window experiments.

    Args:
        war_window_start: First T+N year to include (1=default, 2=skip transition year).
        war_window_end:   Last T+N year to include (3=default, 5=longer window).

    Returns the same schema as ``build_outcomes`` but with ``war_delta`` computed
    from the requested window instead of the fixed T+1..T+3.
    """
    if war_window_end > 5:
        msg = "war_window_end > 5 not supported (view only has T+5)"
        raise ValueError(msg)
    dollar_per_war = compute_empirical_dollar_per_war()
    values_clause = ", ".join(f"({y}, {v})" for y, v in dollar_per_war.items())
    war_cols_recv = " + ".join(
        f"COALESCE(w.war_t_plus_{i}, 0)" for i in range(war_window_start, war_window_end + 1)
    )
    n_years = war_window_end - war_window_start + 1
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            WITH r_recv AS (
                SELECT * FROM (VALUES {values_clause}) AS t(season, dollar_per_war)
            ),
            war_per_trade AS (
                SELECT
                    t.trade_event_id,
                    t.to_team_bref AS receiver_bref,
                    SUM({war_cols_recv}) / NULLIF(COUNT(DISTINCT t.leg_index), 0)
                        AS war_delta,
                    SUM({war_cols_recv}) AS war_received_total,
                    t.trade_season
                FROM trade_player_unified t
                LEFT JOIN trade_player_war_window w
                    ON w.trade_event_id = t.trade_event_id
                    AND w.leg_index = t.leg_index
                WHERE t.to_team_bref IS NOT NULL
                    AND t.trade_season BETWEEN {start_season} AND {end_season}
                GROUP BY t.trade_event_id, t.to_team_bref, t.trade_season
            )
            SELECT
                wpt.trade_event_id,
                wpt.receiver_bref,
                wpt.trade_season,
                wpt.war_delta,
                wpt.war_received_total * COALESCE(r_recv.dollar_per_war, 8000000)
                    AS war_value_received_dollars,
                COALESCE(r_recv.dollar_per_war, 8000000) AS dollar_per_war_season
            FROM war_per_trade wpt
            LEFT JOIN r_recv ON r_recv.season = wpt.trade_season
            """
        ).df()
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
    df["dollar_surplus"] = df["war_value_received_dollars"].fillna(0.0) - df[
        "total_cap_acquired"
    ].fillna(0.0)
    # surplus_wins = dollar_surplus expressed in WAR units.
    # Dividing by the season's market $/WAR converts "dollars above cost" into
    # "wins above what was paid for" — pre-arb cap hits near zero yield surplus_wins
    # close to war_received_total, correctly scoring cheap cost-controlled players.
    df["surplus_wins"] = df["dollar_surplus"] / df["dollar_per_war_season"]
    return df[
        [
            "trade_event_id",
            "receiver_bref",
            "trade_season",
            "war_delta",
            "dollar_surplus",
            "surplus_wins",
        ]
    ]


def build_outcomes(start_season: int = 1990, end_season: int = 2024) -> pd.DataFrame:
    """Build the four-outcome target matrix.

    Returns a DataFrame keyed on (trade_event_id, receiver_bref) with columns:
    xwoba_delta, kpct_delta, war_delta, dollar_surplus.
    """
    dollar_per_war = compute_empirical_dollar_per_war()
    values_clause = ", ".join(f"({y}, {v})" for y, v in dollar_per_war.items())

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
                       AS war_value_given_up_dollars,
                   COALESCE(r_recv.dollar_per_war, 8000000) AS dollar_per_war_season
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
    df["surplus_wins"] = df["dollar_surplus"] / df["dollar_per_war_season"]

    return df[
        [
            "trade_event_id",
            "receiver_bref",
            "trade_season",
            "xwoba_delta",
            "kpct_delta",
            "war_delta",
            "dollar_surplus",
            "surplus_wins",
        ]
    ]
