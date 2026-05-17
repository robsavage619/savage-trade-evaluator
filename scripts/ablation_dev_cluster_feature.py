"""R-14 Ablation A/B: does the analytics-leader-cluster origin signal add predictive value?

Hypothesis test: the R-12/13 descriptive finding that LAD/TBR/SDP/BOS-departed
players underperform HOU/CLE-departed players is encoded as a per-trade feature
``receiver_acquired_from_dev_cluster_score`` (mean of +1/-1/0 across the trade's
acquired players' origin teams). Does adding this feature to the multilevel
Bayesian model improve out-of-time CRPS on the matched-subset test?

Falsifiable: yes => the descriptive R-13 split earns its keep as a predictive
feature. No => the split is real but doesn't improve marginal predictions
beyond what the other 9 features already capture (e.g. receiver dev-fit).
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
ABLATION_FEATURES = [c for c in ALL_FEATURES if c != "receiver_acquired_from_dev_cluster_score"]
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
    """Fit the full-feature model and report the cluster-feature coefficient."""
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
        trace = pm.sample(draws=1000, tune=1000, chains=2, random_seed=SEED, progressbar=False)

    beta_s = trace.posterior["beta"].values.reshape(-1, len(feature_cols))
    print()
    print("=== Feature coefficients (posterior mean, 5%/95% bounds) ===")
    for i, name in enumerate(feature_cols):
        vals = beta_s[:, i]
        sig = "***" if (vals > 0).mean() > 0.975 or (vals < 0).mean() > 0.975 else "   "
        print(
            f"  {name:<48} {vals.mean():>+8.4f}  "
            f"[{np.percentile(vals, 5):>+7.4f}, {np.percentile(vals, 95):>+7.4f}]  {sig}"
        )


def main() -> None:
    """Run both fits on the matched subset and print marginal contribution."""
    df = load_full_subset()
    test = df[df.trade_season >= 2021]
    naive_zero = float(np.abs(test["surplus"]).mean())

    print(f"matched subset: {len(df)} rows total, {len(test)} test rows")
    print(f"predict-zero CRPS (== MAE here): {naive_zero:.4f}")
    print()

    print("=== Fit A: 10 features (with receiver_acquired_from_dev_cluster_score) ===")
    mae_a, crps_a, n_tr, n_te, sigma_a, tau_a = fit_and_score(df, ALL_FEATURES)
    print(f"  train n: {n_tr}, test n: {n_te}, sigma={sigma_a:.4f}, tau_team={tau_a:.4f}")
    print(f"  test MAE  = {mae_a:.4f}  ({100 * (naive_zero - mae_a) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_a:.4f}  ({100 * (naive_zero - crps_a) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Fit B: 9 features (drop dev_cluster_score) ===")
    mae_b, crps_b, n_tr, n_te, sigma_b, tau_b = fit_and_score(df, ABLATION_FEATURES)
    print(f"  train n: {n_tr}, test n: {n_te}, sigma={sigma_b:.4f}, tau_team={tau_b:.4f}")
    print(f"  test MAE  = {mae_b:.4f}  ({100 * (naive_zero - mae_b) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_b:.4f}  ({100 * (naive_zero - crps_b) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Marginal contribution of dev_cluster_score ===")
    print(f"  Δ MAE  (9→10 features): {mae_a - mae_b:+.4f}")
    print(f"  Δ CRPS (9→10 features): {crps_a - crps_b:+.4f}")
    print(f"  Δ tau_team:             {tau_a - tau_b:+.4f}")
    if crps_a < crps_b:
        print("  → dev-cluster feature ADDS predictive signal on the matched subset")
    elif crps_a > crps_b:
        print("  → dev-cluster feature SUBTRACTS predictive signal")
    else:
        print("  → no measurable effect")

    inspect_beta(df)


if __name__ == "__main__":
    main()
