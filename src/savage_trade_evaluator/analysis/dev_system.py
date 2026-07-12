"""Dev-system fingerprint analysis.

Aggregates post-trade pitcher outcome deltas by receiving org to identify
which development systems improve specific skills. Inverts to find pitchers
whose deficiency matches what a target org historically fixes.

Data sources:
  trade_acquired_pitcher_arsenal_features — per-trade K-trajectory + volatility
  statcast_pitcher_percentile_ranks       — current pitcher percentile ranks
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

_MIN_TRADES = 3


def org_fingerprints(min_trades: int = _MIN_TRADES) -> pd.DataFrame:
    """Compute per-org dev-system fingerprint from historical trade outcomes.

    Returns DataFrame with columns:
      receiver_bref, n_trades, avg_k_lift, std_k_lift, avg_vol_lift, z_k_lift.
    Sorted by avg_k_lift descending.
    """
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT
                receiver_bref,
                COUNT(*)                                                   AS n_trades,
                AVG(receiver_acquired_pitcher_k_trajectory)                AS avg_k_lift,
                COVAR_POP(receiver_acquired_pitcher_k_trajectory,
                          receiver_acquired_pitcher_k_trajectory)          AS var_k_lift,
                AVG(receiver_acquired_pitcher_arsenal_volatility)          AS avg_vol_lift
            FROM trade_acquired_pitcher_arsenal_features
            GROUP BY receiver_bref
            HAVING COUNT(*) >= ?
            ORDER BY avg_k_lift DESC
            """,
            [min_trades],
        ).fetchdf()

    if df.empty:
        return df

    import math

    df["std_k_lift"] = df["var_k_lift"].apply(
        lambda v: math.sqrt(float(v)) if v is not None and float(v) >= 0 else None
    )
    df = df.drop(columns=["var_k_lift"])

    # Z-score avg_k_lift across orgs
    mu = float(df["avg_k_lift"].mean())  # type: ignore[arg-type]
    sigma = float(df["avg_k_lift"].std(ddof=1)) if len(df) > 1 else 1.0  # type: ignore[arg-type]
    sigma = sigma if sigma != 0.0 else 1.0
    df["z_k_lift"] = (df["avg_k_lift"] - mu) / sigma

    return df.reset_index(drop=True)


def low_k_candidates(
    season: int,
    k_pct_rank_max: float = 40.0,
) -> pd.DataFrame:
    """Find pitchers with below-average K% who are candidates for dev-system uplift.

    Uses statcast_pitcher_percentile_ranks where the values ARE percentile ranks (0-100).
    Columns: k_percent, bb_percent, whiff_percent, fb_velocity, fb_spin.

    Args:
        season: Season to pull current stats from.
        k_pct_rank_max: Upper bound on K% percentile rank (lower = worse K%).

    Returns:
        DataFrame: player_id, player_name, year, k_percent, whiff_percent, bb_percent, fb_velocity.
    """
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT player_id, player_name, year,
                   k_percent, whiff_percent, bb_percent, fb_velocity, fb_spin
            FROM statcast_pitcher_percentile_ranks
            WHERE year = ?
              AND k_percent IS NOT NULL
              AND k_percent <= ?
            ORDER BY k_percent
            """,
            [season, k_pct_rank_max],
        ).fetchdf()

    return df.reset_index(drop=True)


def match_pitchers_to_orgs(
    season: int,
    k_pct_rank_max: float = 40.0,
    top_orgs: int = 5,
    top_pitchers: int = 15,
) -> dict[str, Any]:
    """Find the best dev-system fits for low-K pitchers.

    Returns a dict with:
      orgs: DataFrame of top K-lifting orgs (org_fingerprints result).
      pitchers: DataFrame of low-K pitcher candidates.
      matches: list of dicts {pitcher_name, team, k_rank, best_fit_org, org_avg_lift}.
    """
    orgs = org_fingerprints()
    pitchers = low_k_candidates(season=season, k_pct_rank_max=k_pct_rank_max)

    if orgs.empty or pitchers.empty:
        return {"orgs": orgs, "pitchers": pitchers, "matches": []}

    top_orgs_df = orgs.head(top_orgs)
    best_org = top_orgs_df.iloc[0]

    matches: list[dict[str, Any]] = []
    for _, p in pitchers.head(top_pitchers).iterrows():
        matches.append(
            {
                "pitcher_name": str(p["player_name"]),
                "k_pct_rank": int(p["k_percent"]) if p["k_percent"] is not None else None,  # type: ignore[arg-type]
                "best_fit_org": str(best_org["receiver_bref"]),
                "org_avg_k_lift": float(best_org["avg_k_lift"]),
            }
        )

    return {"orgs": orgs, "pitchers": pitchers, "matches": matches}
