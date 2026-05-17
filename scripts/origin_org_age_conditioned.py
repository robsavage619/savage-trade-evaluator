"""R-13: Age-conditioned WAR-version origin-org test.

R-12's β_pre coefficient was -1.01 (extreme), partly because pre-WAR is doing
double duty: it absorbs both regression-to-the-mean AND the aging-at-peak
selection (vet traded at career peak → guaranteed to decline next year). By
adding years_since_debut as an explicit covariate, we should:

1. Reduce β_pre's magnitude (it no longer needs to absorb aging).
2. Tighten the per-origin posterior intervals (less unexplained variance).
3. Potentially shift the LAD/HOU/CLE rankings if some orgs systematically
   trade older vs younger players.

We use ``trade_season - first_mlb_year`` (years_since_debut) as the proxy
since true birth-date age isn't in our schema. This is correlated with age
~0.95 in MLB populations (debut age varies ~21-26 with low spread).

The aging-curve literature (Tom Tango, FanGraphs) places peak ~age 27 /
~6 years post-debut. Beyond that, decline is roughly linear. A linear
``β_exp`` term is a first approximation; if a quadratic helps we'll add it.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.storage import db

SEED = 137
ANALYTICS_LEADERS = {"HOU", "TBR", "BOS", "SDP", "CLE"}
MIN_N = 12
MIN_SEASON = 1990


def load_data() -> pd.DataFrame:
    """Load (Δwar, pre_war, experience, season, origin_org) per trade leg."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            WITH first_season AS (
                SELECT mlb_id, MIN(year_id) AS first_mlb_year
                FROM bwar_player_seasons
                WHERE mlb_id IS NOT NULL
                GROUP BY mlb_id
            )
            SELECT w.from_team_bref AS origin,
                   w.to_team_bref AS receiver,
                   w.trade_season,
                   w.war_t_minus_1 AS pre_war,
                   w.war_t_plus_1 - w.war_t_minus_1 AS delta_war,
                   (w.trade_season - fs.first_mlb_year) AS experience
            FROM trade_player_war_window w
            JOIN first_season fs ON fs.mlb_id = w.mlb_player_id
            WHERE w.war_t_minus_1 IS NOT NULL
              AND w.war_t_plus_1 IS NOT NULL
              AND w.from_team_bref IS NOT NULL
              AND w.trade_season >= {MIN_SEASON}
              AND (w.trade_season - fs.first_mlb_year) BETWEEN 0 AND 25
            """
        ).df()
    counts = df.groupby("origin").size()
    keep = counts[counts >= MIN_N].index.tolist()
    df = df[df["origin"].isin(keep)].reset_index(drop=True)
    return df


def fit_multilevel(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Fit Bayesian multilevel model with age covariate."""
    origins = sorted(df["origin"].unique())
    origin_to_idx = {o: i for i, o in enumerate(origins)}
    origin_idx = np.array([origin_to_idx[o] for o in df["origin"]])

    pre_z = (df["pre_war"] - df["pre_war"].mean()) / df["pre_war"].std()
    exp_z = (df["experience"] - df["experience"].mean()) / df["experience"].std()
    season_z = (df["trade_season"] - df["trade_season"].mean()) / df["trade_season"].std()
    y = df["delta_war"].to_numpy(dtype=float)

    with pm.Model(coords={"origin": origins}):
        alpha = pm.Normal("alpha", mu=0.0, sigma=0.5)
        beta_pre = pm.Normal("beta_pre", mu=0.0, sigma=1.0)
        beta_exp = pm.Normal("beta_exp", mu=0.0, sigma=0.5)
        beta_season = pm.Normal("beta_season", mu=0.0, sigma=0.5)
        tau_origin = pm.HalfNormal("tau_origin", sigma=0.5)
        alpha_origin = pm.Normal("alpha_origin", mu=0.0, sigma=tau_origin, dims="origin")
        sigma = pm.HalfNormal("sigma", sigma=2.0)

        mu = (
            alpha
            + alpha_origin[origin_idx]
            + beta_pre * pre_z.to_numpy(dtype=float)
            + beta_exp * exp_z.to_numpy(dtype=float)
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
    print(f"{'param':<14} {'mean':>10} {'sd':>8} {'5%':>10} {'95%':>10}")
    for name in ("alpha", "beta_pre", "beta_exp", "beta_season", "tau_origin", "sigma"):
        vals = trace.posterior[name].values.reshape(-1)
        print(
            f"  {name:<12} {vals.mean():>+10.4f} {vals.std():>8.4f} "
            f"{np.percentile(vals, 5):>+10.4f} {np.percentile(vals, 95):>+10.4f}"
        )

    ao = trace.posterior["alpha_origin"].values
    ao = ao.reshape(-1, len(origins))

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
    return summary, {"alpha_origin_samples": ao, "origins": np.array(origins)}


def main() -> None:
    """Run the age-conditioned multilevel test and print results."""
    df = load_data()
    print(f"Loaded {len(df)} trade legs across {df['origin'].nunique()} origin orgs")
    print(f"Trade-season range: {df['trade_season'].min()}-{df['trade_season'].max()}")
    print(f"Experience range: {int(df['experience'].min())}-{int(df['experience'].max())} years")
    print(f"Experience mean: {df['experience'].mean():.2f} years")
    print()

    summary, samples = fit_multilevel(df)

    print()
    print("=" * 78)
    print("PER-ORIGIN INTERCEPT POSTERIORS (sorted most negative first)")
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
            marker = "<-- NYM (cross-metric flip)"
        print(
            f"{i:>4} {org:<5} {int(row['n']):>4} {row['mean']:>+8.4f} {row['sd']:>6.4f} "
            f"{row['p05']:>+8.4f} {row['p95']:>+8.4f} {row['p_negative']:>6.2%} {marker}"
        )

    print()
    print("=" * 78)
    print("PAIRWISE LAD vs CLEAR-POSITIVE-ORGS — posterior of difference")
    print("=" * 78)
    ao = samples["alpha_origin_samples"]
    origin_list = list(samples["origins"])
    lad_idx = origin_list.index("LAD")
    lad_samples = ao[:, lad_idx]
    for org in ("HOU", "CLE", "MIA", "OAK", "ARI", "STL"):
        if org in origin_list:
            other = ao[:, origin_list.index(org)]
            diff = lad_samples - other
            print(
                f"  LAD - {org}: mean={diff.mean():+.4f}  "
                f"90% CI=[{np.percentile(diff, 5):+.4f}, {np.percentile(diff, 95):+.4f}]  "
                f"P(LAD < {org}) = {(diff < 0).mean():.2%}"
            )


if __name__ == "__main__":
    main()
