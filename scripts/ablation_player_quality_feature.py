"""R-15: ablate per-trade acquired-player-quality feature.

A/B test on whether the rate-based-components player-quality feature adds
predictive value to the multilevel Bayesian model.

This is the first FEATURE engineered under the D-24 architectural rule:
WITHIN-team variation (different trades involve different player mixes), built
from rate-based bWAR components per D-11, NOT from aggregate WAR. The metric
correction Rob flagged: stop using WAR aggregates as outcomes; use components.

Falsifiable: yes => the player-quality dimension is predictively useful and
the D-24 lesson "within-team variation works where team-level features fail"
is validated. No => the existing 10 features already capture this via team
intercepts + receiver-context covariates, and the V1 model is saturated at
its sample size regardless of feature engineering direction.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.bayesian import _crps_empirical
from savage_trade_evaluator.modeling.context_aware import FEATURE_COLUMNS
from savage_trade_evaluator.storage import db

ALL_FEATURES = list(FEATURE_COLUMNS)
ABLATION_FEATURES = [c for c in ALL_FEATURES if c != "receiver_acquired_player_quality"]
SEED = 137


def load_full_subset() -> pd.DataFrame:
    """Trades where ALL features are non-null. Same subset for both fits."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT trade_event_id, trade_season, receiver_bref, surplus,
                   {", ".join(ALL_FEATURES)}
            FROM trade_with_context
            WHERE surplus IS NOT NULL
              AND {" AND ".join(f"{c} IS NOT NULL" for c in ALL_FEATURES)}
            """
        ).df()
    return df


def fit_and_score(
    df: pd.DataFrame, feature_cols: list[str], test_start_season: int = 2021
) -> tuple[float, float, int, int, float, float]:
    """Fit + score. Returns (mae, crps, n_train, n_test, sigma_mean, tau_mean)."""
    train = df[df.trade_season < test_start_season].reset_index(drop=True)
    test = df[df.trade_season >= test_start_season].reset_index(drop=True)

    teams = sorted(set(train["receiver_bref"]) | set(test["receiver_bref"]))
    team_to_idx = {t: i for i, t in enumerate(teams)}

    means = train[feature_cols].mean()
    stds = train[feature_cols].std().replace(0, 1.0)

    def standardize(d: pd.DataFrame) -> np.ndarray:
        return ((d[feature_cols] - means) / stds).to_numpy(dtype=float)

    x_train = standardize(train)
    y_train = train["surplus"].to_numpy(dtype=float)
    team_idx_train = np.array([team_to_idx[t] for t in train["receiver_bref"]])
    x_test = standardize(test)
    y_test = test["surplus"].to_numpy(dtype=float)
    team_idx_test = np.array([team_to_idx[t] for t in test["receiver_bref"]])

    n_teams = len(teams)
    coords = {"team": teams, "feature": feature_cols}
    with pm.Model(coords=coords):
        alpha = pm.Normal("alpha", mu=0.0, sigma=1.0)
        tau_team = pm.HalfNormal("tau_team", sigma=1.0)
        sigma = pm.HalfNormal("sigma", sigma=2.0)
        alpha_team = pm.Normal("alpha_team", mu=0.0, sigma=tau_team, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=0.1, dims="feature")
        mu = alpha + alpha_team[team_idx_train] + pm.math.dot(x_train, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_train)
        trace = pm.sample(
            draws=1500,
            tune=2000,
            chains=4,
            random_seed=SEED,
            progressbar=False,
            target_accept=0.97,
        )

    post = trace.posterior
    n_total = post["alpha"].shape[0] * post["alpha"].shape[1]
    alpha_s = post["alpha"].values.reshape(n_total)
    sigma_s = post["sigma"].values.reshape(n_total)
    tau_s = post["tau_team"].values.reshape(n_total)
    alpha_team_s = post["alpha_team"].values.reshape(n_total, n_teams)
    beta_s = post["beta"].values.reshape(n_total, len(feature_cols))

    team_intercepts = alpha_team_s[:, team_idx_test]
    feat_effects = beta_s @ x_test.T
    mu_post = alpha_s[:, None] + team_intercepts + feat_effects
    rng = np.random.default_rng(SEED)
    noise = rng.normal(0.0, sigma_s[:, None], size=mu_post.shape)
    test_samples = (mu_post + noise).T

    mean_pred = test_samples.mean(axis=1)
    mae = float(np.mean(np.abs(mean_pred - y_test)))
    crps = _crps_empirical(y_test, test_samples)
    return mae, crps, len(train), len(test), float(sigma_s.mean()), float(tau_s.mean())


def inspect_beta(df: pd.DataFrame) -> None:
    """Fit the full-feature model and report all feature coefficients."""
    feature_cols = ALL_FEATURES
    train = df[df.trade_season < 2021].reset_index(drop=True)
    means = train[feature_cols].mean()
    stds = train[feature_cols].std().replace(0, 1.0)
    x_train = ((train[feature_cols] - means) / stds).to_numpy(dtype=float)
    y_train = train["surplus"].to_numpy(dtype=float)
    teams = sorted(set(train["receiver_bref"]))
    team_to_idx = {t: i for i, t in enumerate(teams)}
    team_idx = np.array([team_to_idx[t] for t in train["receiver_bref"]])

    coords = {"team": teams, "feature": feature_cols}
    with pm.Model(coords=coords):
        alpha = pm.Normal("alpha", mu=0.0, sigma=1.0)
        tau_team = pm.HalfNormal("tau_team", sigma=1.0)
        sigma = pm.HalfNormal("sigma", sigma=2.0)
        alpha_team = pm.Normal("alpha_team", mu=0.0, sigma=tau_team, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=0.1, dims="feature")
        mu = alpha + alpha_team[team_idx] + pm.math.dot(x_train, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_train)
        trace = pm.sample(
            draws=1500,
            tune=2000,
            chains=4,
            random_seed=SEED,
            progressbar=False,
            target_accept=0.97,
        )

    beta_s = trace.posterior["beta"].values.reshape(-1, len(feature_cols))
    print()
    print("=== Feature coefficients (posterior mean, 5%/95% bounds) ===")
    for i, name in enumerate(feature_cols):
        vals = beta_s[:, i]
        sig = "***" if (vals > 0).mean() > 0.975 or (vals < 0).mean() > 0.975 else "   "
        mass = max((vals > 0).mean(), (vals < 0).mean())
        print(
            f"  {name:<48} {vals.mean():>+8.4f}  "
            f"[{np.percentile(vals, 5):>+7.4f}, {np.percentile(vals, 95):>+7.4f}]  "
            f"mass={mass:.0%}  {sig}"
        )


def main() -> None:
    """Run both fits on the matched subset and print marginal contribution."""
    df = load_full_subset()
    test = df[df.trade_season >= 2021]
    naive_zero = float(np.abs(test["surplus"]).mean())

    print(f"matched subset: {len(df)} rows total, {len(test)} test rows")
    print(f"predict-zero CRPS (== MAE here): {naive_zero:.4f}")
    print()

    print("=== Fit A: 11 features (with receiver_acquired_player_quality) ===")
    mae_a, crps_a, n_tr, n_te, sigma_a, tau_a = fit_and_score(df, ALL_FEATURES)
    print(f"  train n: {n_tr}, test n: {n_te}, sigma={sigma_a:.4f}, tau_team={tau_a:.4f}")
    print(f"  test MAE  = {mae_a:.4f}  ({100 * (naive_zero - mae_a) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_a:.4f}  ({100 * (naive_zero - crps_a) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Fit B: 10 features (drop player_quality) ===")
    mae_b, crps_b, n_tr, n_te, sigma_b, tau_b = fit_and_score(df, ABLATION_FEATURES)
    print(f"  train n: {n_tr}, test n: {n_te}, sigma={sigma_b:.4f}, tau_team={tau_b:.4f}")
    print(f"  test MAE  = {mae_b:.4f}  ({100 * (naive_zero - mae_b) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_b:.4f}  ({100 * (naive_zero - crps_b) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Marginal contribution of player_quality ===")
    print(f"  Δ MAE  (10→11 features): {mae_a - mae_b:+.4f}")
    print(f"  Δ CRPS (10→11 features): {crps_a - crps_b:+.4f}")
    print(f"  Δ tau_team:              {tau_a - tau_b:+.4f}")
    if crps_a < crps_b:
        pct = 100 * (crps_b - crps_a) / crps_b
        print(
            f"  → player-quality feature ADDS predictive signal "
            f"(Δ CRPS = {crps_a - crps_b:+.4f}, {pct:.2f}% improvement)"
        )
    elif crps_a > crps_b:
        print("  → player-quality feature SUBTRACTS predictive signal")
    else:
        print("  → no measurable effect")

    inspect_beta(df)


if __name__ == "__main__":
    main()
