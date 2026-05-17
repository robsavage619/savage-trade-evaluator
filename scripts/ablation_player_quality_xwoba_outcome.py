"""R-19: re-ablate player-quality against a rate-based (non-WAR) outcome.

R-15 showed receiver_acquired_player_quality has +87% directional mass on
the WAR-derivative surplus. Open caveat: surplus = war_received - war_given_up,
so player_quality (built from WAR components) is mechanically correlated.

This script reruns the same ablation against `xwoba_delta_mean` from the
trade_xwoba_outcome view — the average post-trade xwOBA change of acquired
hitters with Statcast data. If the player_quality signal survives this
outcome with comparable directional mass, R-15's finding was not WAR-circular.
If it collapses, R-15 was partly mechanical.
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


def load_subset() -> pd.DataFrame:
    """Trades with the rate-based xwOBA outcome AND all the features non-null."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT twc.trade_event_id, twc.trade_season, twc.receiver_bref,
                   txo.xwoba_delta_mean AS outcome,
                   {", ".join("twc." + c for c in ALL_FEATURES)}
            FROM trade_with_context twc
            JOIN trade_xwoba_outcome txo
                ON txo.trade_event_id = twc.trade_event_id
                AND txo.receiver_bref = twc.receiver_bref
            WHERE txo.xwoba_delta_mean IS NOT NULL
              AND {" AND ".join(f"twc.{c} IS NOT NULL" for c in ALL_FEATURES)}
            """
        ).df()
    return df


def fit_and_score(
    df: pd.DataFrame, feature_cols: list[str], test_start_season: int = 2021
) -> tuple[float, float, np.ndarray]:
    """Fit + score; return mae, crps, beta posterior samples."""
    train = df[df.trade_season < test_start_season].reset_index(drop=True)
    test = df[df.trade_season >= test_start_season].reset_index(drop=True)

    teams = sorted(set(train["receiver_bref"]) | set(test["receiver_bref"]))
    team_to_idx = {t: i for i, t in enumerate(teams)}

    means = train[feature_cols].mean()
    stds = train[feature_cols].std().replace(0, 1.0)
    y_scale = train["outcome"].std()

    def standardize(d: pd.DataFrame) -> np.ndarray:
        return ((d[feature_cols] - means) / stds).to_numpy(dtype=float)

    x_train = standardize(train)
    y_train = train["outcome"].to_numpy(dtype=float)
    team_idx_train = np.array([team_to_idx[t] for t in train["receiver_bref"]])
    x_test = standardize(test)
    y_test = test["outcome"].to_numpy(dtype=float)
    team_idx_test = np.array([team_to_idx[t] for t in test["receiver_bref"]])

    n_teams = len(teams)
    coords = {"team": teams, "feature": feature_cols}
    with pm.Model(coords=coords):
        alpha = pm.Normal("alpha", mu=0.0, sigma=y_scale)
        tau_team = pm.HalfNormal("tau_team", sigma=y_scale)
        sigma = pm.HalfNormal("sigma", sigma=y_scale * 2)
        alpha_team = pm.Normal("alpha_team", mu=0.0, sigma=tau_team, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=y_scale / 2, dims="feature")
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
    return mae, crps, beta_s


def main() -> None:
    """Run ablation A/B with rate-based xwOBA outcome."""
    df = load_subset()
    test = df[df.trade_season >= 2021]
    naive_zero = float(np.abs(test["outcome"]).mean())
    print(f"matched subset: {len(df)} rows, {len(test)} test rows")
    print(f"outcome scale (mean abs xwoba_delta): {naive_zero:.4f}")
    print()

    print(f"=== Fit A: {len(ALL_FEATURES)} features (with player_quality) ===")
    mae_a, crps_a, beta_a = fit_and_score(df, ALL_FEATURES)
    print(f"  MAE = {mae_a:.4f}  CRPS = {crps_a:.4f}")
    print()

    print(f"=== Fit B: {len(ABLATION_FEATURES)} features (drop player_quality) ===")
    mae_b, crps_b, _ = fit_and_score(df, ABLATION_FEATURES)
    print(f"  MAE = {mae_b:.4f}  CRPS = {crps_b:.4f}")
    print()

    print("=== Marginal contribution of player_quality on xwOBA-outcome ===")
    print(
        f"  Δ CRPS = {crps_a - crps_b:+.4f}  ({100 * (crps_b - crps_a) / crps_b:+.3f}% improvement)"
    )
    print()

    print("=== Coefficients on xwOBA-outcome (sorted by directional mass) ===")
    coef_rows = []
    for i, name in enumerate(ALL_FEATURES):
        vals = beta_a[:, i]
        mass = max((vals > 0).mean(), (vals < 0).mean())
        coef_rows.append((mass, name, vals.mean(), np.percentile(vals, 5), np.percentile(vals, 95)))
    coef_rows.sort(reverse=True)
    for mass, name, mean, p5, p95 in coef_rows:
        marker = "  <-- TEST FEATURE" if name == "receiver_acquired_player_quality" else ""
        print(f"  mass={mass:.0%}  {name:<52} {mean:>+9.5f}  [{p5:>+8.5f}, {p95:>+8.5f}]{marker}")


if __name__ == "__main__":
    main()
