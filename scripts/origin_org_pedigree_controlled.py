"""Pedigree-controlled per-origin-org system-tax test (R-10).

Multilevel regression of post-trade xwOBA delta on:
  - pre-trade xwOBA (absorbs regression to the mean)
  - trade-season trend (absorbs league-wide era shifts)
  - receiver-org hitter dev-fit (absorbs "where they went" effect)
  - origin-org random intercept (THE test statistic)

The origin-org intercepts represent each origin's post-trade dropoff residual
after controlling for the player's pre-trade tier and where they ended up.
A negative LAD intercept that doesn't overlap zero — and is more negative
than the analytics-leader comp set (HOU/TBR/BOS/SDP/CLE) — would support
the system-tax thesis specifically for LAD.

Selection-on-trades caveat: this test cannot distinguish "LAD inflates
production via system" from "LAD sells high more aggressively than others."
Both predict the same residual sign. Requires synthetic-control to separate.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
ANALYTICS_LEADERS = {"HOU", "TBR", "BOS", "SDP", "CLE"}
MIN_N = 8  # min trades per origin to include


def load_data() -> pd.DataFrame:
    """Load (Δxwoba, pre_xwoba, season, receiver_dev_fit, origin_org) per trade leg."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT w.from_team_bref AS origin,
                   w.to_team_bref AS receiver,
                   w.trade_season,
                   w.xwoba_t_minus_1 AS pre_xwoba,
                   w.xwoba_t_plus_1 - w.xwoba_t_minus_1 AS delta_xwoba,
                   COALESCE(tsf.org_hitter_xwoba_jump_3yr, 0.0) AS receiver_dev_fit
            FROM trade_player_xwoba_window w
            LEFT JOIN team_season_features tsf
                ON tsf.bref_code = w.to_team_bref AND tsf.season = w.trade_season
            WHERE w.xwoba_t_minus_1 IS NOT NULL
              AND w.xwoba_t_plus_1 IS NOT NULL
              AND w.from_team_bref IS NOT NULL
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

    # Standardize continuous covariates
    pre_z = (df["pre_xwoba"] - df["pre_xwoba"].mean()) / df["pre_xwoba"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    rdf_z = (df["receiver_dev_fit"] - df["receiver_dev_fit"].mean()) / (
        df["receiver_dev_fit"].std() if df["receiver_dev_fit"].std() > 0 else 1.0
    )
    y = df["delta_xwoba"].to_numpy(dtype=float)

    with pm.Model(coords={"origin": origins}):
        # league-wide intercept
        alpha = pm.Normal("alpha", mu=0.0, sigma=0.05)
        # covariates
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=0.1)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=0.05)
        beta_rdf = pm.Normal("beta_rdf", mu=0.0, sigma=0.05)
        # origin random intercepts with partial pooling
        tau_origin = pm.HalfNormal("tau_origin", sigma=0.05)
        alpha_origin = pm.Normal("alpha_origin", mu=0.0, sigma=tau_origin, dims="origin")
        # observation noise
        sigma = pm.HalfNormal("sigma", sigma=0.2)

        mu = (
            alpha
            + alpha_origin[origin_idx]
            + beta_pre * pre_z.to_numpy(dtype=float)
            + beta_season * season_z.to_numpy(dtype=float)
            + beta_rdf * rdf_z.to_numpy(dtype=float)
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

    # Population-level effects
    print()
    print("=" * 78)
    print("POPULATION-LEVEL POSTERIORS")
    print("=" * 78)
    for name in ("alpha", "beta_pre", "beta_season", "beta_rdf", "tau_origin", "sigma"):
        vals = trace.posterior[name].values.reshape(-1)
        print(
            f"  {name:<14} mean={vals.mean():>+8.4f}  sd={vals.std():.4f}  "
            f"5%={np.percentile(vals, 5):>+8.4f}  95%={np.percentile(vals, 95):>+8.4f}"
        )

    # Origin-specific intercept posteriors
    ao = trace.posterior["alpha_origin"].values  # (chain, draw, origin)
    ao = ao.reshape(-1, len(origins))

    summary = pd.DataFrame(
        {
            "origin": origins,
            "n": [int((df["origin"] == o).sum()) for o in origins],
            "mean": ao.mean(axis=0),
            "sd": ao.std(axis=0),
            "p05": np.percentile(ao, 5, axis=0),
            "p25": np.percentile(ao, 25, axis=0),
            "p75": np.percentile(ao, 75, axis=0),
            "p95": np.percentile(ao, 95, axis=0),
            "p_negative": (ao < 0).mean(axis=0),
        }
    ).sort_values("mean")
    return summary


def main() -> None:
    """Run the pedigree-controlled multilevel test."""
    df = load_data()
    print(f"Loaded {len(df)} trade legs across {df['origin'].nunique()} origin orgs")
    print(f"Trade-season range: {df['trade_season'].min()}-{df['trade_season'].max()}")
    print()

    summary = fit_multilevel(df)

    print()
    print("=" * 78)
    print("PER-ORIGIN INTERCEPT POSTERIORS (sorted most negative first)")
    print("Negative = post-trade dropoff GREATER than the player's pre-trade tier predicts")
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
        print(
            f"{i:>4} {org:<5} {int(row['n']):>4} {row['mean']:>+8.4f} {row['sd']:>6.4f} "
            f"{row['p05']:>+8.4f} {row['p95']:>+8.4f} {row['p_negative']:>6.2%} {marker}"
        )

    # Direct LAD-vs-comp comparison
    print()
    print("=" * 78)
    print("LAD vs ANALYTICS-LEADER PAIRWISE POSTERIOR DIFFERENCES")
    print("=" * 78)
    # Need raw posterior to do this — re-fit and keep arrays. Simpler: recompute.
    # Actually we don't have the trace here; just summarize from the table.
    lad_row = summary[summary["origin"] == "LAD"].iloc[0]
    print(f"  LAD intercept: mean={lad_row['mean']:+.4f}, P(<0) = {lad_row['p_negative']:.2%}")
    for org in ("HOU", "TBR", "BOS", "SDP", "CLE"):
        if org in summary["origin"].values:
            row = summary[summary["origin"] == org].iloc[0]
            print(
                f"  {org} intercept: mean={row['mean']:+.4f}, "
                f"P(<0) = {row['p_negative']:.2%}, "
                f"diff (LAD - {org}) = {lad_row['mean'] - row['mean']:+.4f}"
            )


if __name__ == "__main__":
    main()
