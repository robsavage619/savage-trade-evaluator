"""Ablation A/B: does the per-coach hitter xwOBA-jump feature add signal?

The 8-feature fit on the 702-row subset (rows where the coach feature is
non-null) gave -3.15% CRPS vs predict-zero. The 7-feature fit was +1.05% but
on a different 911-row subset. This script holds the subset constant.
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
ABLATION_FEATURES = [c for c in ALL_FEATURES if c != "receiver_coach_hitter_xwoba_jump_3yr"]
SEED = 137


def load_full_subset() -> pd.DataFrame:
    """Trades where ALL 8 features are non-null. Same subset for both fits."""
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
    """Fit + score. Returns (test_mae, test_crps, n_train, n_test, sigma, tau_team)."""
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
            draws=1000, tune=1000, chains=2, random_seed=SEED, progressbar=False
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


def main() -> None:
    """Run both fits on the matched subset and print the marginal-contribution table."""
    df = load_full_subset()
    test = df[df.trade_season >= 2021]
    naive_zero = float(np.abs(test["surplus"]).mean())

    print(f"matched subset: {len(df)} rows total, {len(test)} test rows")
    print(f"predict-zero CRPS (== MAE here): {naive_zero:.4f}")
    print()

    print("=== Fit A: 8 features (with per-coach hitter feature) ===")
    mae_8, crps_8, n_tr_8, n_te_8, sigma_8, tau_8 = fit_and_score(df, ALL_FEATURES)
    print(f"  train n: {n_tr_8}, test n: {n_te_8}")
    print(f"  sigma={sigma_8:.4f}, tau_team={tau_8:.4f}")
    print(f"  test MAE  = {mae_8:.4f}  ({100 * (naive_zero - mae_8) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_8:.4f}  ({100 * (naive_zero - crps_8) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Fit B: 7 features (drop per-coach hitter feature) ===")
    mae_7, crps_7, n_tr_7, n_te_7, sigma_7, tau_7 = fit_and_score(df, ABLATION_FEATURES)
    print(f"  train n: {n_tr_7}, test n: {n_te_7}")
    print(f"  sigma={sigma_7:.4f}, tau_team={tau_7:.4f}")
    print(f"  test MAE  = {mae_7:.4f}  ({100 * (naive_zero - mae_7) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_7:.4f}  ({100 * (naive_zero - crps_7) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Marginal contribution of per-coach hitter feature ===")
    print(f"  Δ MAE  (7→8 features): {mae_8 - mae_7:+.4f}")
    print(f"  Δ CRPS (7→8 features): {crps_8 - crps_7:+.4f}")
    print(f"  Δ tau_team:            {tau_8 - tau_7:+.4f}")
    if crps_8 < crps_7:
        print("  → per-coach feature ADDS predictive signal on the matched subset")
    elif crps_8 > crps_7:
        print("  → per-coach feature SUBTRACTS predictive signal")
    else:
        print("  → no measurable effect")


if __name__ == "__main__":
    main()
