"""R-33: V2 (team, regime) vs V1 (team-only) ablation on identical data.

There is no standalone V1 module on the V2 feature/outcome matrix — the
legacy ``modeling/bayesian.py`` is hardwired to a different feature set
and outcome. So we fit an inline V1 baseline here (single-level: alpha0
plus per-team intercept plus beta·x, no regime nesting) on the same
``assemble_combined()`` matrix V2 uses. The only architectural difference
between the two fits is the regime-nesting layer.

Reports per outcome:
- V1 / V2 train/test MAE + CRPS + 90% coverage
- credible feature counts and the V1-only / V2-only / shared sets
- one-line verdict
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.v2.backtest import (
    OUTCOME_FEATURES,
    _crps_empirical,
    assemble_combined,
    backtest_outcome,
)
from savage_trade_evaluator.modeling.v2.features import filter_complete_cases


def _impute_and_split(
    outcome: str, train_end: int = 2020, test_end: int = 2024, min_present: int = 5
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    feature_cols = OUTCOME_FEATURES[outcome]
    combined = assemble_combined()
    combined = combined[combined[outcome].notna()].copy()
    present = combined[list(feature_cols)].notna().sum(axis=1)
    complete = combined[present >= min_present].copy()
    for c in feature_cols:
        complete[c] = complete[c].astype("float64")
        complete[c] = complete[c].fillna(complete[c].mean())
    train = complete[complete["trade_season"] <= train_end].reset_index(drop=True)
    test = complete[
        (complete["trade_season"] > train_end) & (complete["trade_season"] <= test_end)
    ].reset_index(drop=True)
    return train, test, feature_cols


def _fit_v1_team_only(
    train: pd.DataFrame, outcome: str, feature_cols: tuple[str, ...]
) -> dict:
    """Fit single-level model: alpha0 + alpha_team + beta·x, no regime."""
    teams = tuple(sorted(train["receiver_bref"].unique()))
    team_to_idx = {t: i for i, t in enumerate(teams)}
    team_idx = np.array([team_to_idx[t] for t in train["receiver_bref"]])

    means = train[list(feature_cols)].mean()
    stds = train[list(feature_cols)].std().replace(0, 1.0)
    x = ((train[list(feature_cols)] - means) / stds).to_numpy(dtype=float)
    y = train[outcome].to_numpy(dtype=float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    coords = {"team": list(teams), "feature": list(feature_cols)}
    with pm.Model(coords=coords):
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        tau_team = pm.HalfNormal("tau_team", sigma=1.0)
        alpha_team_z = pm.Normal("alpha_team_z", mu=0.0, sigma=1.0, dims="team")
        alpha_team = pm.Deterministic("alpha_team", alpha_team_z * tau_team, dims="team")
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + alpha_team[team_idx] + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=1500, tune=2000, chains=4, random_seed=137,
            progressbar=False, target_accept=0.99,
        )
    return {
        "trace": trace, "teams": teams, "team_to_idx": team_to_idx,
        "feature_cols": feature_cols, "means": means, "stds": stds,
        "y_mean": y_mean, "y_std": y_std,
    }


def _v1_predict(fit: dict, df: pd.DataFrame) -> np.ndarray:
    cols = list(fit["feature_cols"])
    x_test = ((df[cols] - fit["means"]) / fit["stds"]).to_numpy(dtype=float)
    post = fit["trace"].posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    sigma_s = post["sigma"].values.reshape(n_samples)
    beta_s = post["beta"].values.reshape(n_samples, len(cols))
    alpha_team_s = post["alpha_team"].values.reshape(n_samples, len(fit["teams"]))
    team_idx = np.array([fit["team_to_idx"].get(t, -1) for t in df["receiver_bref"]])
    out = np.zeros((len(df), n_samples))
    for i in range(len(df)):
        tidx = team_idx[i]
        team_a = alpha_team_s[:, tidx] if tidx >= 0 else 0.0
        mu = alpha0_s + team_a + beta_s @ x_test[i]
        rng = np.random.default_rng(137 + i)
        noise = rng.normal(0.0, sigma_s)
        out[i] = (mu + noise) * fit["y_std"] + fit["y_mean"]
    return out


def _credible_set(trace, feature_cols: tuple[str, ...]) -> set[str]:
    beta = trace.posterior["beta"].values.reshape(-1, len(feature_cols))
    out = set()
    for i, name in enumerate(feature_cols):
        v = beta[:, i]
        p05 = float(np.percentile(v, 5))
        p95 = float(np.percentile(v, 95))
        mass = max((v > 0).mean(), (v < 0).mean())
        ci_excludes_zero = (p05 > 0 and p95 > 0) or (p05 < 0 and p95 < 0)
        if ci_excludes_zero and mass >= 0.95:
            out.add(name)
    return out


def main() -> None:
    """Run V1-vs-V2 ablation across all four outcomes."""
    rows = []
    outcomes = ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus")
    for o in outcomes:
        print()
        print("#" * 88)
        print(f"# {o.upper()}")
        print("#" * 88)

        # V2 (existing harness)
        v2_result = backtest_outcome(
            outcome=o, train_end_season=2020, test_end_season=2024,
            minimum_features_present=5,
        )
        v2_credible = set(
            v2_result.credible_features.loc[
                v2_result.credible_features["credible"], "feature"
            ].tolist()
        )

        # V1 inline (same data, no regime)
        train, test, feature_cols = _impute_and_split(o)
        if len(train) < 50:
            print(f"  SKIPPED: only {len(train)} train rows")
            continue
        v1_fit = _fit_v1_team_only(train, o, feature_cols)
        v1_credible = _credible_set(v1_fit["trace"], feature_cols)

        v1_pred = _v1_predict(v1_fit, test)
        y_test = test[o].to_numpy(dtype=float)
        v1_mae = float(np.mean(np.abs(v1_pred.mean(axis=1) - y_test)))
        v1_crps = _crps_empirical(y_test, v1_pred)
        p05 = np.percentile(v1_pred, 5, axis=1)
        p95 = np.percentile(v1_pred, 95, axis=1)
        v1_cov = float(((y_test >= p05) & (y_test <= p95)).mean())

        only_v1 = v1_credible - v2_credible
        only_v2 = v2_credible - v1_credible
        shared = v1_credible & v2_credible

        print(f"  V1 (team-only):  MAE={v1_mae:.4f}  CRPS={v1_crps:.4f}  "
              f"cov90={v1_cov:.1%}  credible={len(v1_credible)}")
        print(f"  V2 (team+regime):MAE={v2_result.test_mae:.4f}  "
              f"CRPS={v2_result.test_crps:.4f}  "
              f"cov90={v2_result.coverage_90:.1%}  credible={len(v2_credible)}")
        print(f"  shared credible: {sorted(shared) or '(none)'}")
        print(f"  V1-only:         {sorted(only_v1) or '(none)'}")
        print(f"  V2-only:         {sorted(only_v2) or '(none)'}")
        delta = len(v2_credible) - len(v1_credible)
        verdict = (
            f"V2 adds {delta} credible features over V1" if delta > 0
            else f"V1 finds {-delta} more credible features than V2" if delta < 0
            else "V1 and V2 tied on credible-feature count"
        )
        print(f"  verdict: {verdict}")

        rows.append({
            "outcome": o,
            "v1_mae": v1_mae, "v2_mae": v2_result.test_mae,
            "v1_crps": v1_crps, "v2_crps": v2_result.test_crps,
            "v1_cov90": v1_cov, "v2_cov90": v2_result.coverage_90,
            "v1_credible": len(v1_credible), "v2_credible": len(v2_credible),
            "shared": len(shared), "only_v1": len(only_v1), "only_v2": len(only_v2),
        })

    print()
    print("=" * 88)
    print("R-33 SUMMARY")
    print("=" * 88)
    if rows:
        df = pd.DataFrame(rows)
        print(df.to_string(index=False))


if __name__ == "__main__":
    main()
