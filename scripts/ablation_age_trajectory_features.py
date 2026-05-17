"""R-18: ablate avg-experience and war-trajectory features.

Two more within-team-variation features per D-24, both player-level
aggregations of acquired-player career stage and recent momentum.

Falsifiable: either or both pass the 87%-mass directional threshold
R-15 set, or they sit at noise. CRPS movement is secondary signal.
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
NEW_FEATURES = {
    "receiver_acquired_player_avg_experience",
    "receiver_acquired_player_avg_war_trajectory",
}
ABLATION_FEATURES = [c for c in ALL_FEATURES if c not in NEW_FEATURES]
SEED = 137


def load_subset() -> pd.DataFrame:
    """Return matched-subset rows with all features non-null."""
    with db.connect(read_only=True) as conn:
        return conn.execute(
            f"""
            SELECT trade_event_id, trade_season, receiver_bref, surplus,
                   {", ".join(ALL_FEATURES)}
            FROM trade_with_context
            WHERE surplus IS NOT NULL
              AND {" AND ".join(f"{c} IS NOT NULL" for c in ALL_FEATURES)}
            """
        ).df()


def fit_and_score(
    df: pd.DataFrame, feature_cols: list[str], test_start_season: int = 2021
) -> tuple[float, float, np.ndarray, list[str]]:
    """Fit + score; return mae, crps, beta posterior samples, feature list."""
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
    return mae, crps, beta_s, feature_cols


def main() -> None:
    """Run ablation A/B and inspect feature coefficients."""
    df = load_subset()
    test = df[df.trade_season >= 2021]
    naive_zero = float(np.abs(test["surplus"]).mean())
    print(f"matched subset: {len(df)} rows, {len(test)} test rows")
    print(f"predict-zero CRPS: {naive_zero:.4f}")
    print()

    print(f"=== Fit A: {len(ALL_FEATURES)} features (full set) ===")
    mae_a, crps_a, beta_a, cols_a = fit_and_score(df, ALL_FEATURES)
    print(
        f"  MAE = {mae_a:.4f}  CRPS = {crps_a:.4f}  "
        f"({100 * (naive_zero - crps_a) / naive_zero:+.2f}% vs 0)"
    )
    print()

    print(f"=== Fit B: {len(ABLATION_FEATURES)} features (drop age + war-trajectory) ===")
    mae_b, crps_b, _, _ = fit_and_score(df, ABLATION_FEATURES)
    print(
        f"  MAE = {mae_b:.4f}  CRPS = {crps_b:.4f}  "
        f"({100 * (naive_zero - crps_b) / naive_zero:+.2f}% vs 0)"
    )
    print()

    print("=== Marginal contribution of the TWO new features combined ===")
    print(f"  Δ MAE  = {mae_a - mae_b:+.4f}")
    print(
        f"  Δ CRPS = {crps_a - crps_b:+.4f}  ({100 * (crps_b - crps_a) / crps_b:+.3f}% improvement)"
    )
    print()

    print("=== Full-model feature coefficients (sorted by directional mass) ===")
    coef_rows = []
    for i, name in enumerate(cols_a):
        vals = beta_a[:, i]
        mass = max((vals > 0).mean(), (vals < 0).mean())
        coef_rows.append((mass, name, vals.mean(), np.percentile(vals, 5), np.percentile(vals, 95)))
    coef_rows.sort(reverse=True)
    for mass, name, mean, p5, p95 in coef_rows:
        sig = "***" if mass > 0.975 else "** " if mass > 0.95 else "   "
        marker = "  <-- NEW" if name in NEW_FEATURES else ""
        print(
            f"  mass={mass:.0%}  {name:<52} {mean:>+8.4f}  "
            f"[{p5:>+7.4f}, {p95:>+7.4f}]  {sig}{marker}"
        )


if __name__ == "__main__":
    main()
