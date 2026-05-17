"""R-17: Cross-metric replication of R-13 pairwise origin-org comparisons.

R-13 found that even when LAD's marginal intercept can't be credibly
separated from zero, pairwise comparisons LAD vs HOU/CLE/etc carry signal
(P(LAD < HOU) = 70%, etc). But R-13 used WAR. R-16 found WAR conclusions
don't always hold under rate-based metrics.

This script reruns the pairwise comparison on three outcome metrics:
- xwOBA (hitter quality-of-contact, Statcast 2015+)
- WAR (the R-13 version, all-era)
- K% (pitcher arsenal, Statcast 2015+)

The bar for "robust" per-org finding (D-25): replicates across at least
two metrics. The bar is comparative, not absolute — we expect single-org
marginals to be wide; we care whether pairwise rankings agree.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
MIN_N = 5
ANALYTICS_LEADERS = ("HOU", "CLE", "TBR", "SDP", "BOS")


def _load(query: str) -> pd.DataFrame:
    with db.connect(read_only=True) as conn:
        return conn.execute(query).df()


def fit(df: pd.DataFrame, outcome_col: str, pre_col: str) -> tuple[np.ndarray, list[str]]:
    """Run multilevel; return per-origin posterior samples."""
    origins = sorted(df["origin"].unique())
    o2i = {o: i for i, o in enumerate(origins)}
    o_idx = np.array([o2i[o] for o in df["origin"]])

    pre_z = (df[pre_col] - df[pre_col].mean()) / df[pre_col].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df[outcome_col].to_numpy(dtype=float)
    y_scale = float(np.std(y))

    with pm.Model(coords={"origin": origins}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=y_scale)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=y_scale * 2)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=y_scale)
        tau = pm.HalfNormal("tau_origin", sigma=y_scale)
        alpha_origin = pm.Normal("alpha_origin", mu=0.0, sigma=tau, dims="origin")
        sigma = pm.HalfNormal("sigma", sigma=y_scale * 2)
        mu = (
            alpha
            + alpha_origin[o_idx]
            + beta_pre * pre_z.to_numpy(dtype=float)
            + beta_season * season_z.to_numpy(dtype=float)
        )
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y)
        trace = pm.sample(
            draws=2000,
            tune=2000,
            chains=4,
            random_seed=SEED,
            progressbar=False,
            target_accept=0.95,
        )
    ao = trace.posterior["alpha_origin"].values.reshape(-1, len(origins))
    return ao, origins


def pairwise_table(ao: np.ndarray, origins: list[str], anchor: str) -> dict[str, float]:
    """Return P(anchor < other) for each non-anchor origin."""
    if anchor not in origins:
        return {}
    a_idx = origins.index(anchor)
    a_samples = ao[:, a_idx]
    return {
        o: float((a_samples - ao[:, i] < 0).mean()) for i, o in enumerate(origins) if o != anchor
    }


def load_xwoba() -> pd.DataFrame:
    """xwOBA-outcome rows from trade_player_xwoba_window."""
    df = _load("""
        SELECT from_team_bref AS origin, trade_season,
               xwoba_t_minus_1 AS pre,
               (xwoba_t_plus_1 - xwoba_t_minus_1) AS delta
        FROM trade_player_xwoba_window
        WHERE xwoba_t_minus_1 IS NOT NULL AND xwoba_t_plus_1 IS NOT NULL
          AND from_team_bref IS NOT NULL
    """)
    counts = df.groupby("origin").size()
    return df[df["origin"].isin(counts[counts >= MIN_N].index)].reset_index(drop=True)


def load_war() -> pd.DataFrame:
    """WAR-outcome rows from trade_player_war_window (1990+)."""
    df = _load("""
        SELECT from_team_bref AS origin, trade_season,
               war_t_minus_1 AS pre,
               (war_t_plus_1 - war_t_minus_1) AS delta
        FROM trade_player_war_window
        WHERE war_t_minus_1 IS NOT NULL AND war_t_plus_1 IS NOT NULL
          AND from_team_bref IS NOT NULL AND trade_season >= 1990
    """)
    counts = df.groupby("origin").size()
    return df[df["origin"].isin(counts[counts >= 12].index)].reset_index(drop=True)


def load_kpct() -> pd.DataFrame:
    """K%-outcome rows from trade_player_arsenal_window."""
    df = _load("""
        SELECT from_team_bref AS origin, trade_season,
               k_percent_t_minus_1 AS pre,
               (k_percent_t_plus_1 - k_percent_t_minus_1) AS delta
        FROM trade_player_arsenal_window
        WHERE k_percent_t_minus_1 IS NOT NULL AND k_percent_t_plus_1 IS NOT NULL
          AND from_team_bref IS NOT NULL
    """)
    counts = df.groupby("origin").size()
    return df[df["origin"].isin(counts[counts >= MIN_N].index)].reset_index(drop=True)


def main() -> None:
    """Run pairwise comparison LAD vs analytics-leader cluster across three metrics."""
    results: dict[str, dict[str, float]] = {}
    sample_sizes: dict[str, int] = {}
    for label, loader in [("xwOBA", load_xwoba), ("WAR", load_war), ("K%", load_kpct)]:
        df = loader()
        sample_sizes[label] = len(df)
        print(f"\nFitting {label} (n={len(df)})...")
        ao, origins = fit(df, "delta", "pre")
        results[label] = pairwise_table(ao, origins, "LAD")
        if "LAD" not in origins:
            print(f"  LAD not in {label} sample (insufficient n)")

    print("\n" + "=" * 78)
    print("LAD vs ANALYTICS-LEADER CLUSTER, P(LAD < other) across metrics")
    print("=" * 78)
    print(f"{'opponent':<10} {'xwOBA':>10} {'WAR':>10} {'K%':>10}  cross-metric-robust?")
    for org in ANALYTICS_LEADERS:
        row = []
        for label in ("xwOBA", "WAR", "K%"):
            v = results[label].get(org)
            row.append(f"{v * 100:>9.1f}%" if v is not None else f"{'—':>10}")
        # robust = signal consistent (>=60% in same direction) across at least 2 of 3
        vals = [results[m].get(org) for m in ("xwOBA", "WAR", "K%")]
        vals_clean = [v for v in vals if v is not None]
        consistent = sum(1 for v in vals_clean if v >= 0.60)
        flag = "ROBUST" if consistent >= 2 else ("partial" if consistent == 1 else "no")
        print(f"  vs {org:<6}" + "".join(row) + f"   {flag}")

    print()
    print("Sample sizes:")
    for k, v in sample_sizes.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
