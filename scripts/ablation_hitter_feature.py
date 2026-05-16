"""Ablation A/B: does the hitter dev-fit feature beat zero on its own merits?

The 7-feature fit (Phase 3 V1) showed +1.05% CRPS improvement over predict-zero.
The 6-feature fit (Phase 3 V0) showed +3.33% — but on a *different, larger* test
set (985 rows vs 911), because dropping the hitter feature relaxes the
``IS NOT NULL`` row filter.

This script holds the subset constant: fit BOTH variants on the same 911-row
subset (rows that have all 7 features non-null) and report the CRPS delta.
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
ABLATION_FEATURES = [c for c in ALL_FEATURES if c != "receiver_org_hitter_xwoba_jump_3yr"]
SEED = 137


def load_full_subset() -> pd.DataFrame:
    """Trades where ALL 7 features are non-null. Same subset for both fits."""
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
    df: pd.DataFrame,
    feature_cols: list[str],
    test_start_season: int = 2021,
    n_samples: int = 1000,
    n_tune: int = 1000,
    n_chains: int = 2,
) -> tuple[float, float, int, int]:
    """Fit + score. Returns (test_mae, test_crps, n_train, n_test)."""
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
            draws=n_samples, tune=n_tune, chains=n_chains,
            random_seed=SEED, progressbar=False,
        )

    post = trace.posterior
    n_total = post["alpha"].shape[0] * post["alpha"].shape[1]
    alpha_s = post["alpha"].values.reshape(n_total)
    sigma_s = post["sigma"].values.reshape(n_total)
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
    return mae, crps, len(train), len(test)


def main() -> None:
    """Run both fits on the matched subset and print the marginal-contribution table."""
    df = load_full_subset()
    test = df[df.trade_season >= 2021]
    naive_zero = float(np.abs(test["surplus"]).mean())

    print(f"matched subset: {len(df)} rows total, {len(test)} test rows")
    print(f"predict-zero CRPS (== MAE here): {naive_zero:.4f}")
    print()

    print("=== Fit A: 7 features (with hitter dev-fit) ===")
    mae_7, crps_7, n_train_7, n_test_7 = fit_and_score(df, ALL_FEATURES)
    print(f"  train n: {n_train_7}, test n: {n_test_7}")
    print(f"  test MAE  = {mae_7:.4f}  ({100 * (naive_zero - mae_7) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_7:.4f}  ({100 * (naive_zero - crps_7) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Fit B: 6 features (drop hitter dev-fit) ===")
    mae_6, crps_6, n_train_6, n_test_6 = fit_and_score(df, ABLATION_FEATURES)
    print(f"  train n: {n_train_6}, test n: {n_test_6}")
    print(f"  test MAE  = {mae_6:.4f}  ({100 * (naive_zero - mae_6) / naive_zero:+.2f}% vs 0)")
    print(f"  test CRPS = {crps_6:.4f}  ({100 * (naive_zero - crps_6) / naive_zero:+.2f}% vs 0)")
    print()

    print("=== Marginal contribution of hitter feature (apples-to-apples) ===")
    print(f"  Δ MAE  (6→7 features): {mae_7 - mae_6:+.4f}")
    print(f"  Δ CRPS (6→7 features): {crps_7 - crps_6:+.4f}")
    if crps_7 < crps_6:
        print("  → hitter feature ADDS predictive signal on the matched subset")
    elif crps_7 > crps_6:
        print("  → hitter feature SUBTRACTS predictive signal (model loses calibration)")
    else:
        print("  → no measurable effect")


if __name__ == "__main__":
    main()
