"""R-29: data archaeology on TEX-Daniels and the Anthopoulos sign flip.

R-28 surfaced these as findings the full ranking implies but our prior
analyses ignored. This script does NOT do new modeling — it surfaces the
actual underlying trades so we can read what drove each finding.

Two questions:
1. TEX-Daniels (-0.040 WAR intercept, P(<0)=70%, n=66 trade legs). Is it a
   few catastrophic trades or a broad pattern? Who were the biggest losers?
2. Anthopoulos in TOR (+0.027) vs ATL (-0.023). Same GM, opposite signal.
   Is the difference roster-driven, era-driven, or a few outlier trades?
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db


def regime_trades(regime_id: str, limit: int = 30) -> pd.DataFrame:
    """Return per-leg trade outcomes for one regime, sorted by Δ WAR ascending (worst→best)."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT w.trade_season, w.date, tpu.player_name,
                   w.from_team_bref AS origin,
                   w.to_team_bref AS to_team,
                   w.war_t_minus_1 AS pre,
                   w.war_t_plus_1 AS post,
                   (w.war_t_plus_1 - w.war_t_minus_1) AS delta
            FROM trade_player_war_window w
            JOIN trade_player_unified tpu
                ON tpu.trade_event_id = w.trade_event_id
                AND tpu.leg_index = w.leg_index
            JOIN team_regime_assignments tra
                ON tra.bref_code = w.from_team_bref
                AND tra.season = w.trade_season
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND tra.regime_id = '{regime_id}'
            ORDER BY delta ASC
            LIMIT {limit}
            """
        ).df()
    return df


def regime_summary(regime_id: str) -> dict[str, float]:
    """Distributional stats for a regime's trades."""
    with db.connect(read_only=True) as conn:
        r = conn.execute(
            f"""
            SELECT
                COUNT(*) AS n,
                AVG(war_t_plus_1 - war_t_minus_1) AS mean_delta,
                MEDIAN(war_t_plus_1 - war_t_minus_1) AS median_delta,
                STDDEV_SAMP(war_t_plus_1 - war_t_minus_1) AS sd_delta,
                AVG(war_t_minus_1) AS mean_pre,
                AVG(war_t_plus_1) AS mean_post,
                MIN(war_t_plus_1 - war_t_minus_1) AS worst,
                MAX(war_t_plus_1 - war_t_minus_1) AS best
            FROM trade_player_war_window w
            JOIN team_regime_assignments tra
                ON tra.bref_code = w.from_team_bref
                AND tra.season = w.trade_season
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND tra.regime_id = '{regime_id}'
            """
        ).fetchone()
    return {
        "n": r[0],
        "mean_delta": r[1],
        "median_delta": r[2],
        "sd_delta": r[3],
        "mean_pre": r[4],
        "mean_post": r[5],
        "worst": r[6],
        "best": r[7],
    }


def print_regime_section(label: str, regime_id: str, n_extremes: int = 8) -> None:
    """Print a regime's summary stats and most-extreme trades both directions."""
    print("\n" + "=" * 90)
    print(f"  {label}: {regime_id}")
    print("=" * 90)
    s = regime_summary(regime_id)
    print(f"  n trades       : {s['n']}")
    print(f"  pre-WAR mean   : {s['mean_pre']:+.3f}")
    print(f"  post-WAR mean  : {s['mean_post']:+.3f}")
    print(f"  Δ WAR mean     : {s['mean_delta']:+.3f}")
    print(f"  Δ WAR median   : {s['median_delta']:+.3f}")
    print(f"  Δ WAR std-dev  : {s['sd_delta']:.3f}")
    print(f"  worst-Δ trade  : {s['worst']:+.2f} WAR")
    print(f"  best-Δ trade   : {s['best']:+.2f} WAR")

    # Most-negative-delta legs (biggest flops AFTER leaving this regime)
    df_worst = regime_trades(regime_id, limit=n_extremes)
    print(f"\n  Top {n_extremes} BIGGEST POST-TRADE DROPS (departed-and-flopped):")
    for _, row in df_worst.iterrows():
        print(
            f"    {row['trade_season']}  {str(row['player_name'])[:22]:<22} "
            f"→ {row['to_team']:<4}  pre={row['pre']:>+4.1f}  post={row['post']:>+4.1f}  "
            f"Δ={row['delta']:>+5.2f}"
        )

    # Most-positive-delta legs (biggest GAINS after leaving this regime)
    with db.connect(read_only=True) as conn:
        df_best = conn.execute(
            f"""
            SELECT w.trade_season, tpu.player_name,
                   w.to_team_bref AS to_team,
                   w.war_t_minus_1 AS pre,
                   w.war_t_plus_1 AS post,
                   (w.war_t_plus_1 - w.war_t_minus_1) AS delta
            FROM trade_player_war_window w
            JOIN trade_player_unified tpu
                ON tpu.trade_event_id = w.trade_event_id
                AND tpu.leg_index = w.leg_index
            JOIN team_regime_assignments tra
                ON tra.bref_code = w.from_team_bref
                AND tra.season = w.trade_season
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND tra.regime_id = '{regime_id}'
            ORDER BY delta DESC
            LIMIT {n_extremes}
            """
        ).df()
    print(f"\n  Top {n_extremes} BIGGEST POST-TRADE GAINS (departed-and-thrived):")
    for _, row in df_best.iterrows():
        print(
            f"    {row['trade_season']}  {str(row['player_name'])[:22]:<22} "
            f"→ {row['to_team']:<4}  pre={row['pre']:>+4.1f}  post={row['post']:>+4.1f}  "
            f"Δ={row['delta']:>+5.2f}"
        )


def trim_check(regime_id: str) -> None:
    """How sensitive is the regime intercept to its 3 worst and 3 best trades?"""
    with db.connect(read_only=True) as conn:
        all_deltas = conn.execute(
            f"""
            SELECT war_t_plus_1 - war_t_minus_1 AS delta
            FROM trade_player_war_window w
            JOIN team_regime_assignments tra
                ON tra.bref_code = w.from_team_bref
                AND tra.season = w.trade_season
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND tra.regime_id = '{regime_id}'
            ORDER BY delta
            """
        ).df()
    deltas = all_deltas["delta"].values
    mean_full = deltas.mean()
    mean_trim = deltas[3:-3].mean() if len(deltas) > 7 else mean_full
    print(
        f"\n  Sensitivity: mean Δ all={mean_full:+.4f}  "
        f"trimmed-3-worst-and-3-best={mean_trim:+.4f}  "
        f"shift={mean_trim - mean_full:+.4f}"
    )


def main() -> None:
    """Investigate TEX-Daniels and the Anthopoulos sign flip."""
    print_regime_section("STRONGEST NEGATIVE", "TEX_Jon Daniels")
    trim_check("TEX_Jon Daniels")
    print_regime_section("ANTHOPOULOS — Toronto (positive)", "TOR_Alex Anthopoulos")
    trim_check("TOR_Alex Anthopoulos")
    print_regime_section("ANTHOPOULOS — Atlanta (negative)", "ATL_Alex Anthopoulos")
    trim_check("ATL_Alex Anthopoulos")


if __name__ == "__main__":
    main()
