"""R-16: Origin-org system-tax test using pitcher arsenal K% as outcome.

R-10 used xwOBA (hitter quality-of-contact). R-12/13 used WAR (aggregate).
R-16 uses Statcast K% percentile rank — the cleanest pitcher-side rate metric
we have. Tests Rob's metric-skepticism: does the LAD-vs-HOU/CLE pattern
that survives WAR also show up in arsenal-percentile-space, or was it an
artifact of WAR's playing-time/defensive-noise encoding?

The MVP Machine Ch 9 thesis is specifically about K%-installation under
Strom: pitchers acquired by HOU show K% jumps post-trade. Origin-side
mirror: do pitchers DEPARTING HOU keep their K%? Do pitchers departing
LAD lose theirs?

Outcome: k_percent_t_plus_1 - k_percent_t_minus_1.
Sample bounded to Statcast era (2015+), much smaller than the WAR test.
Per-origin n will be ~5-15. Pairwise posteriors are the right framing.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
ANALYTICS_LEADERS = {"HOU", "TBR", "BOS", "SDP", "CLE"}
MIN_N = 5


def load_data() -> pd.DataFrame:
    """Load (Δk_pct, pre_k_pct, season, origin_org) per pitcher trade leg."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT w.from_team_bref AS origin,
                   w.to_team_bref AS receiver,
                   w.trade_season,
                   w.k_percent_t_minus_1 AS pre_k,
                   w.k_percent_t_plus_1 - w.k_percent_t_minus_1 AS delta_k
            FROM trade_player_arsenal_window w
            WHERE w.k_percent_t_minus_1 IS NOT NULL
              AND w.k_percent_t_plus_1 IS NOT NULL
              AND w.from_team_bref IS NOT NULL
            """
        ).df()
    counts = df.groupby("origin").size()
    keep = counts[counts >= MIN_N].index.tolist()
    df = df[df["origin"].isin(keep)].reset_index(drop=True)
    return df


def fit_multilevel(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Fit Bayesian multilevel model; return summary + posterior samples + origin list."""
    origins = sorted(df["origin"].unique())
    origin_to_idx = {o: i for i, o in enumerate(origins)}
    origin_idx = np.array([origin_to_idx[o] for o in df["origin"]])

    pre_z = (df["pre_k"] - df["pre_k"].mean()) / df["pre_k"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df["delta_k"].to_numpy(dtype=float)

    with pm.Model(coords={"origin": origins}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=10.0)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=20.0)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=10.0)
        tau_origin = pm.HalfNormal("tau_origin", sigma=10.0)
        alpha_origin = pm.Normal("alpha_origin", mu=0.0, sigma=tau_origin, dims="origin")
        sigma = pm.HalfNormal("sigma", sigma=20.0)

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
            f"  {name:<12} mean={vals.mean():>+8.3f}  sd={vals.std():.3f}  "
            f"5%={np.percentile(vals, 5):>+8.3f}  95%={np.percentile(vals, 95):>+8.3f}"
        )

    ao = trace.posterior["alpha_origin"].values.reshape(-1, len(origins))
    summary = pd.DataFrame(
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
    return summary, ao, origins


def main() -> None:
    """Run R-16 origin-org test on pitcher K% delta."""
    df = load_data()
    print(f"Loaded {len(df)} pitcher trade legs across {df['origin'].nunique()} origin orgs")
    print(f"Trade-season range: {df['trade_season'].min()}-{df['trade_season'].max()}")
    print(
        f"Pre-K% range: {df['pre_k'].min():.1f}-{df['pre_k'].max():.1f}, "
        f"mean delta: {df['delta_k'].mean():+.2f}"
    )
    print()

    summary, ao, origins = fit_multilevel(df)

    print()
    print("=" * 78)
    print("PER-ORIGIN INTERCEPT POSTERIORS (negative = departed pitchers LOSE K%)")
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
            marker = "<-- NYM"
        print(
            f"{i:>4} {org:<5} {int(row['n']):>4} {row['mean']:>+8.3f} {row['sd']:>6.3f} "
            f"{row['p05']:>+8.3f} {row['p95']:>+8.3f} {row['p_negative']:>6.2%} {marker}"
        )

    print()
    print("=" * 78)
    print("PAIRWISE: LAD vs analytics-leader cluster (the R-13 framing)")
    print("=" * 78)
    if "LAD" in origins:
        lad_idx = origins.index("LAD")
        lad_samples = ao[:, lad_idx]
        for org in ("HOU", "CLE", "TBR", "BOS", "SDP"):
            if org in origins:
                other = ao[:, origins.index(org)]
                diff = lad_samples - other
                print(
                    f"  LAD - {org}: mean={diff.mean():+.3f}  "
                    f"90% CI=[{np.percentile(diff, 5):+.3f}, {np.percentile(diff, 95):+.3f}]  "
                    f"P(LAD < {org}) = {(diff < 0).mean():.2%}"
                )


if __name__ == "__main__":
    main()
