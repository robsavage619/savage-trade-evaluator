"""R-34: V0 / V1 / V2 bracket — does the multilevel structure pay off at all?

R-33 found V2 (team + regime) ≈ V1 (team-only). The natural next question:
does the team layer itself pay off, or is the regime-and-team scaffolding
all overhead?

V0: alpha0 + beta·x                  (population intercept only)
V1: alpha0 + alpha_team + beta·x     (team-level partial pooling)
V2: alpha0 + alpha_regime + beta·x   (team + GM-regime nesting)

If V0 ≈ V1 ≈ V2 → drop the multilevel; collapse to OLS / ridge.
If V0 << V1 ≈ V2 → drop regime layer, keep team-only V1.
If V0 < V1 < V2 → keep V2 as designed (the original hypothesis).
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


def _fit_v0(
    train: pd.DataFrame, outcome: str, feature_cols: tuple[str, ...]
) -> dict:
    """V0: population intercept + features only. No team, no regime."""
    means = train[list(feature_cols)].mean()
    stds = train[list(feature_cols)].std().replace(0, 1.0)
    x = ((train[list(feature_cols)] - means) / stds).to_numpy(dtype=float)
    y = train[outcome].to_numpy(dtype=float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    coords = {"feature": list(feature_cols)}
    with pm.Model(coords=coords):
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=1500, tune=2000, chains=4, random_seed=137,
            progressbar=False, target_accept=0.99,
        )
    return {
        "trace": trace, "feature_cols": feature_cols, "means": means, "stds": stds,
        "y_mean": y_mean, "y_std": y_std,
    }


def _v0_predict(fit: dict, df: pd.DataFrame) -> np.ndarray:
    cols = list(fit["feature_cols"])
    x_test = ((df[cols] - fit["means"]) / fit["stds"]).to_numpy(dtype=float)
    post = fit["trace"].posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    sigma_s = post["sigma"].values.reshape(n_samples)
    beta_s = post["beta"].values.reshape(n_samples, len(cols))
    out = np.zeros((len(df), n_samples))
    for i in range(len(df)):
        mu = alpha0_s + beta_s @ x_test[i]
        rng = np.random.default_rng(137 + i)
        noise = rng.normal(0.0, sigma_s)
        out[i] = (mu + noise) * fit["y_std"] + fit["y_mean"]
    return out


def _credible_count(trace, feature_cols: tuple[str, ...]) -> int:
    beta = trace.posterior["beta"].values.reshape(-1, len(feature_cols))
    n = 0
    for i in range(len(feature_cols)):
        v = beta[:, i]
        p05 = float(np.percentile(v, 5))
        p95 = float(np.percentile(v, 95))
        mass = max((v > 0).mean(), (v < 0).mean())
        ci_excludes_zero = (p05 > 0 and p95 > 0) or (p05 < 0 and p95 < 0)
        if ci_excludes_zero and mass >= 0.95:
            n += 1
    return n


def main() -> None:
    """V0/V1/V2 bracket across all four outcomes."""
    # Pull V1 from R-33 (re-fit inline since it's quick) — actually just call V2 backtest
    # for V2 metrics, fit V0 inline, and import V1 numbers from the same harness.
    rows = []
    for o in ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus"):
        print()
        print("#" * 88)
        print(f"# {o.upper()}")
        print("#" * 88)
        train, test, feature_cols = _impute_and_split(o)
        if len(train) < 50:
            print(f"  SKIPPED: only {len(train)} train rows")
            continue

        # V0
        v0_fit = _fit_v0(train, o, feature_cols)
        v0_cred = _credible_count(v0_fit["trace"], feature_cols)
        v0_pred = _v0_predict(v0_fit, test)
        y_test = test[o].to_numpy(dtype=float)
        v0_mae = float(np.mean(np.abs(v0_pred.mean(axis=1) - y_test)))
        v0_crps = _crps_empirical(y_test, v0_pred)
        p05 = np.percentile(v0_pred, 5, axis=1)
        p95 = np.percentile(v0_pred, 95, axis=1)
        v0_cov = float(((y_test >= p05) & (y_test <= p95)).mean())

        # V2 (reuse existing harness)
        v2_result = backtest_outcome(
            outcome=o, train_end_season=2020, test_end_season=2024,
            minimum_features_present=5,
        )
        v2_cred = int(v2_result.credible_features["credible"].sum())

        print(f"  V0 (no team):  MAE={v0_mae:.4f}  CRPS={v0_crps:.4f}  "
              f"cov90={v0_cov:.1%}  credible={v0_cred}")
        print(f"  V2 (team+reg): MAE={v2_result.test_mae:.4f}  "
              f"CRPS={v2_result.test_crps:.4f}  "
              f"cov90={v2_result.coverage_90:.1%}  credible={v2_cred}")

        rows.append({
            "outcome": o,
            "v0_mae": v0_mae, "v2_mae": v2_result.test_mae,
            "v0_crps": v0_crps, "v2_crps": v2_result.test_crps,
            "v0_cov90": v0_cov, "v2_cov90": v2_result.coverage_90,
            "v0_credible": v0_cred, "v2_credible": v2_cred,
        })

    print()
    print("=" * 88)
    print("R-34 SUMMARY (V1 numbers from R-33 — V1 ≈ V2 already established)")
    print("=" * 88)
    if rows:
        print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
