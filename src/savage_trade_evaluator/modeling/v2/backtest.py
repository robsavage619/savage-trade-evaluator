"""V2 backtest harness — out-of-time train/test on each outcome.

Train: 1990-2020 (or whatever fits per-outcome era constraints).
Test:  2021-2024 (out-of-time, no leakage).
Metrics: CRPS, MAE, 90% CI calibration, per-quartile coverage.

Per D-26 the primary diagnostic is **coefficient credibility**, not point-
prediction accuracy. CRPS on small test sets is unreliable; the calibration
plot and credible-feature count tell us if V2 is improving over V1.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v2.features import (
    ALL_FEATURES,
    build_feature_matrix,
    filter_complete_cases,
)
from savage_trade_evaluator.modeling.v2.multilevel import (
    V2FitResult,
    coefficient_summary,
    fit_multilevel_v2,
)
from savage_trade_evaluator.modeling.v2.outcomes import build_outcomes

# Map outcome name → which feature subset is meaningful for it.
# This drives feature selection per outcome (per D-27).
OUTCOME_FEATURES: dict[str, tuple[str, ...]] = {
    "xwoba_delta": ALL_FEATURES,
    "kpct_delta": ALL_FEATURES,
    "war_delta": ALL_FEATURES,
    "dollar_surplus": ALL_FEATURES,
}


@dataclass(frozen=True, slots=True)
class V2BacktestResult:
    """Container for one outcome's backtest results."""

    outcome: str
    fit: V2FitResult
    train_n: int
    test_n: int
    test_crps: float
    test_mae: float
    coverage_90: float  # fraction of test points within the 90% predicted CI
    credible_features: pd.DataFrame
    test_predictions: pd.DataFrame


def _crps_empirical(y: np.ndarray, samples: np.ndarray) -> float:
    """Empirical CRPS via samples-vs-truth. y shape (n,), samples shape (n, m)."""
    # CRPS = E|X - y| - 0.5 E|X - X'|, approximated via samples.
    n, m = samples.shape
    term1 = np.mean(np.abs(samples - y[:, None]))
    sorted_samples = np.sort(samples, axis=1)
    # E|X - X'| ≈ 2/(m(m-1)) * sum over sorted differences
    diffs = np.diff(sorted_samples, axis=1).sum(axis=1)
    term2 = 0.5 * np.mean(2.0 * diffs / m)
    return float(term1 - term2)


def assemble_combined(outcomes_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build features + outcomes joined on (trade_event_id, receiver_bref).

    Args:
        outcomes_df: Optional pre-built outcomes DataFrame. If None, calls
            ``build_outcomes()`` with defaults. Pass a custom outcomes frame to
            swap in alternative windows (Q-02 5yr, Q-07 shifted).
    """
    features_df = build_feature_matrix()
    if outcomes_df is None:
        outcomes_df = build_outcomes()
    merged = features_df.merge(
        outcomes_df,
        on=["trade_event_id", "receiver_bref", "trade_season"],
        how="inner",
    )
    return merged


def backtest_outcome(
    outcome: str,
    train_end_season: int = 2020,
    test_end_season: int = 2024,
    minimum_features_present: int | None = None,
) -> V2BacktestResult:
    """Run one outcome's full backtest pipeline.

    Returns V2BacktestResult with fit, predictions, and metrics.
    """
    feature_cols = OUTCOME_FEATURES[outcome]
    combined = assemble_combined()

    # Apply per-outcome filter: drop rows where the outcome is null.
    combined = combined[combined[outcome].notna()].copy()

    # Drop rows missing required features (allow partial coverage of some
    # features if minimum_features_present is set).
    if minimum_features_present is None:
        complete = filter_complete_cases(combined, feature_cols)
    else:
        present = combined[list(feature_cols)].notna().sum(axis=1)
        complete = combined[present >= minimum_features_present].copy()
        # Cast feature cols to float64 (some come back as Int64 from DuckDB)
        # then impute remaining NaNs with the column mean.
        for c in feature_cols:
            complete[c] = complete[c].astype("float64")
            complete[c] = complete[c].fillna(complete[c].mean())

    train = complete[complete["trade_season"] <= train_end_season].reset_index(drop=True)
    test = complete[
        (complete["trade_season"] > train_end_season)
        & (complete["trade_season"] <= test_end_season)
    ].reset_index(drop=True)

    if len(train) < 50:
        msg = (
            f"V2 outcome={outcome}: only {len(train)} train rows after filtering; "
            "abort and check data layer."
        )
        raise ValueError(msg)

    fit = fit_multilevel_v2(
        df=train,
        outcome_col=outcome,
        feature_cols=feature_cols,
    )

    # Predict on test
    test_pred = _predict(fit, test)
    test_y = test[outcome].to_numpy(dtype=float)
    test_samples = test_pred  # shape (n_test, n_posterior_samples)

    mean_pred = test_samples.mean(axis=1)
    mae = float(np.mean(np.abs(mean_pred - test_y)))
    crps = _crps_empirical(test_y, test_samples)

    # 90% coverage
    p05 = np.percentile(test_samples, 5, axis=1)
    p95 = np.percentile(test_samples, 95, axis=1)
    coverage_90 = float(((test_y >= p05) & (test_y <= p95)).mean())

    creds = coefficient_summary(fit)

    test_predictions = test[["trade_event_id", "receiver_bref", "trade_season"]].copy()
    test_predictions["y_true"] = test_y
    test_predictions["y_pred_mean"] = mean_pred
    test_predictions["y_pred_p05"] = p05
    test_predictions["y_pred_p95"] = p95

    return V2BacktestResult(
        outcome=outcome,
        fit=fit,
        train_n=len(train),
        test_n=len(test),
        test_crps=crps,
        test_mae=mae,
        coverage_90=coverage_90,
        credible_features=creds,
        test_predictions=test_predictions,
    )


def _predict(fit: V2FitResult, df: pd.DataFrame) -> np.ndarray:
    """Posterior-predictive samples for a held-out set. Shape (n_rows, n_samples)."""
    cols = list(fit.feature_cols)
    x_test = ((df[cols] - fit.feature_means) / fit.feature_stds).to_numpy(dtype=float)
    post = fit.trace.posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    sigma_s = post["sigma"].values.reshape(n_samples)
    beta_s = post["beta"].values.reshape(n_samples, len(cols))
    alpha_regime_s = post["alpha_regime"].values.reshape(n_samples, len(fit.regimes))

    # Map test regimes to indices, fallback to team-only if absent
    regime_to_idx = {r: i for i, r in enumerate(fit.regimes)}
    regime_idx = np.array([regime_to_idx.get(r, -1) for r in df["regime_id"]])

    # For unknown regimes, use team-mean alpha (alpha_team[team] ~ regime[regime] avg)
    # Practically: 0 contribution beyond alpha0 + features.
    n_test = len(df)
    out = np.zeros((n_test, n_samples))
    for i in range(n_test):
        ridx = regime_idx[i]
        team_alpha = alpha_regime_s[:, ridx] if ridx >= 0 else 0.0
        mu = alpha0_s + team_alpha + beta_s @ x_test[i]
        rng = np.random.default_rng(137 + i)
        noise = rng.normal(0.0, sigma_s)
        # Convert back from z-units to outcome units
        out[i] = (mu + noise) * fit.y_std + fit.y_mean
    return out


def print_backtest_report(result: V2BacktestResult) -> None:
    """Plain-English summary of one backtest outcome."""
    print("=" * 88)
    print(f"V2 BACKTEST: outcome={result.outcome}")
    print("=" * 88)
    print(f"  Train n: {result.train_n}, Test n: {result.test_n}")
    print(f"  Test MAE:    {result.test_mae:.4f}")
    print(f"  Test CRPS:   {result.test_crps:.4f}")
    print(f"  90% coverage: {result.coverage_90:.1%}  (target: 90%)")
    print()
    print("CREDIBLE FEATURES (D-26 threshold: 90% CI excludes zero AND mass >= 95%):")
    cred = result.credible_features[result.credible_features["credible"]]
    if cred.empty:
        print("  (none cleared the credibility threshold)")
    else:
        for _, r in cred.iterrows():
            sign = "+" if r["mean_beta"] > 0 else ""
            print(
                f"  *** {r['feature']:<48}  beta={sign}{r['mean_beta']:.4f}  "
                f"[{r['p05']:+.3f}, {r['p95']:+.3f}]  mass={r['directional_mass']:.0%}"
            )
    print()
    print("DIRECTIONAL FEATURES (mass >= 85% but not credible):")
    direc = result.credible_features[
        (~result.credible_features["credible"])
        & (result.credible_features["directional_mass"] >= 0.85)
    ]
    if direc.empty:
        print("  (none)")
    else:
        for _, r in direc.iterrows():
            sign = "+" if r["mean_beta"] > 0 else ""
            print(
                f"    {r['feature']:<48}  beta={sign}{r['mean_beta']:.4f}  "
                f"[{r['p05']:+.3f}, {r['p95']:+.3f}]  mass={r['directional_mass']:.0%}"
            )
