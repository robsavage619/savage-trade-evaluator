"""R-12: WAR-version of the origin-org system-tax test on the expanded sample.

Mirror of scripts/origin_org_pedigree_controlled.py (R-10) but:
- Outcome: Δ WAR (war_t_plus_1 - war_t_minus_1) instead of Δ xwOBA
- Pre-trade control: war_t_minus_1
- Sample: bWAR 1871+ coverage, no Statcast 2015+ floor. Trade-event side now
  includes ~4,551 pre-2010 Retrosheet trades (R-11), expanding the sample
  ~2.5x relative to R-10.
- Receiver dev-fit covariate dropped because team_season_features dev-fit
  variables (org_hitter_xwoba_jump_3yr etc.) are Statcast-era only and would
  re-introduce a 2015+ filter, defeating the whole point of using R-11 data.

Filter to trade_season >= 1990 to stay in the modern multi-team-divided
free-agency era. Pre-1990 is sparse, structurally different (no FA market
yet for the earliest decades), and would inject heterogeneity that the
single covariate (pre-WAR) can't absorb.

WAR-specific confound: counting WAR is sensitive to playing-time recovery.
A young player traded from a stacked roster (LAD) to a rebuild gets more
PT and his counting WAR rises. The pre_war control absorbs the baseline,
but PT-recovery itself is correlated with origin-org tendencies — orgs
that block prospects WILL produce trades where the departed player gains
WAR via more PT. Read the LAD/HOU sign accordingly.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
ANALYTICS_LEADERS = {"HOU", "TBR", "BOS", "SDP", "CLE"}
MIN_N = 12  # min trades per origin to include (raised from 8 given larger sample)
MIN_SEASON = 1990


def load_data() -> pd.DataFrame:
    """Load (Δwar, pre_war, season, origin_org) per trade leg with bWAR coverage."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT w.from_team_bref AS origin,
                   w.to_team_bref AS receiver,
                   w.trade_season,
                   w.war_t_minus_1 AS pre_war,
                   w.war_t_plus_1 - w.war_t_minus_1 AS delta_war
            FROM trade_player_war_window w
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND w.from_team_bref IS NOT NULL
              AND w.trade_season >= {MIN_SEASON}
            """
        ).df()
    counts = df.groupby("origin").size()
    keep = counts[counts >= MIN_N].index.tolist()
    df = df[df["origin"].isin(keep)].reset_index(drop=True)
    return df


def fit_multilevel(df: pd.DataFrame) -> pd.DataFrame:
    """Fit Bayesian multilevel model; return per-origin intercept posterior summary."""
    origins = sorted(df["origin"].unique())
    origin_to_idx = {o: i for i, o in enumerate(origins)}
    origin_idx = np.array([origin_to_idx[o] for o in df["origin"]])

    pre_z = (df["pre_war"] - df["pre_war"].mean()) / df["pre_war"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df["delta_war"].to_numpy(dtype=float)

    with pm.Model(coords={"origin": origins}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=0.5)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=1.0)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=0.5)
        tau_origin = pm.HalfNormal("tau_origin", sigma=0.5)
        alpha_origin = pm.Normal("alpha_origin", mu=0.0, sigma=tau_origin, dims="origin")
        sigma = pm.HalfNormal("sigma", sigma=2.0)

        mu = (
            alpha
            + alpha_origin[origin_idx]
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

    print()
    print("=" * 78)
    print("POPULATION-LEVEL POSTERIORS")
    print("=" * 78)
    for name in ("alpha", "beta_pre", "beta_season", "tau_origin", "sigma"):
        vals = trace.posterior[name].values.reshape(-1)
        print(
            f"  {name:<14} mean={vals.mean():>+8.4f}  sd={vals.std():.4f}  "
            f"5%={np.percentile(vals, 5):>+8.4f}  95%={np.percentile(vals, 95):>+8.4f}"
        )

    ao = trace.posterior["alpha_origin"].values
    ao = ao.reshape(-1, len(origins))

    return pd.DataFrame(
        {
            "origin": origins,
            "n": [int((df["origin"] == o).sum()) for o in origins],
            "mean": ao.mean(axis=0),
            "sd": ao.std(axis=0),
            "p05": np.percentile(ao, 5, axis=0),
            "p95": np.percentile(ao, 95, axis=0),
            "p_negative": (ao < 0).mean(axis=0),
        }
    ).sort_values("mean")


def main() -> None:
    """Run the WAR-version pedigree-controlled multilevel test."""
    df = load_data()
    print(f"Loaded {len(df)} trade legs across {df['origin'].nunique()} origin orgs")
    print(f"Trade-season range: {df['trade_season'].min()}-{df['trade_season'].max()}")
    print(f"Min legs per origin to include: {MIN_N}")
    print()

    summary = fit_multilevel(df)

    print()
    print("=" * 78)
    print("PER-ORIGIN INTERCEPT POSTERIORS (sorted most negative first)")
    print("Negative = Δ WAR worse than the player's pre-trade WAR tier predicts")
    print("=" * 78)
    print(
        f"{'rank':>4} {'org':<5} {'n':>4} {'mean':>8} {'sd':>6} "
        f"{'[5%':>8} {'95%]':>8} {'P(<0)':>6} marker"
    )
    for i, (_, row) in enumerate(summary.iterrows(), 1):
        org = row["origin"]
        marker = ""
        if org == "LAD":
            marker = "<-- LAD (Rob's thesis)"
        elif org in ANALYTICS_LEADERS:
            marker = "<-- analytics leader"
        elif org == "NYM":
            marker = "<-- NYM (R-10 surprise outlier)"
        print(
            f"{i:>4} {org:<5} {int(row['n']):>4} {row['mean']:>+8.4f} {row['sd']:>6.4f} "
            f"{row['p05']:>+8.4f} {row['p95']:>+8.4f} {row['p_negative']:>6.2%} {marker}"
        )

    print()
    print("=" * 78)
    print("KEY-ORG COMPARISON (LAD vs NYM vs analytics leaders)")
    print("=" * 78)
    targets = ("LAD", "NYM", "HOU", "TBR", "BOS", "SDP", "CLE")
    for org in targets:
        if org in summary["origin"].values:
            row = summary[summary["origin"] == org].iloc[0]
            print(
                f"  {org:<4} n={int(row['n']):>3}  mean={row['mean']:+.4f}  "
                f"90% CI=[{row['p05']:+.4f}, {row['p95']:+.4f}]  "
                f"P(<0)={row['p_negative']:.2%}"
            )


if __name__ == "__main__":
    main()
