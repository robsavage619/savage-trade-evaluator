"""V3 multilevel — team partial pooling as a random intercept.

Per D-28: origin-org effects are regime-specific (90% within-team variance).
This module is the first rung: team-level partial pooling with no regime
nesting (the full (team, regime) nesting is deferred until front_office
regime boundaries are wired in as coordinates).

Architecture:
    alpha_team ~ Normal(0, sigma_team)   # per-receiver partial pooling
    sigma_team ~ HalfNormal(0.5)         # tighter prior than V2 (R-34/35 showed
                                         # tau_team → 0 under a 1.0 prior)
    mu_i = alpha0 + alpha_team[team_i] + beta · x_i
    y_i  ~ Normal(mu_i, sigma)

Non-centered parameterization throughout to avoid funnel geometry.

R-33/34/35 found that team-level pooling added zero signal when team-aggregate
features were also in the model. This module respects D-27: the caller chooses
the feature set, and the D-26 credible-feature diagnostic is the signal check.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.v2.backtest import _crps_empirical
from savage_trade_evaluator.modeling.v3 import (
    V3BacktestResult,
    V3FitResult,
    V3_OUTCOME_FEATURES,
    _split_and_impute,
    assemble_v3_combined,
    coefficient_summary,
)


def fit_v3_multilevel(
    train: pd.DataFrame,
    outcome: str,
    feature_cols: tuple[str, ...],
    draws: int = 1500,
    tune: int = 2000,
    chains: int = 4,
    seed: int = 137,
    target_accept: float = 0.99,
) -> V3FitResult:
    """Fit V3 + team partial pooling on one outcome.

    Identical signature to ``fit_v3``; returns the same ``V3FitResult``
    so all downstream callers (predict, coefficient_summary, backtest) are
    reusable without modification.

    Args:
        train: Training rows with outcome and feature columns present.
        outcome: Target column name.
        feature_cols: Predictor columns (already imputed by caller).
        draws / tune / chains / seed / target_accept: PyMC sample kwargs.

    Returns:
        V3FitResult with trace. alpha_team samples are accessible in
        trace.posterior["alpha_team"] for regime-extension work.
    """
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
        # Tighter half-normal prior than V2: R-34/35 showed tau_team → 0
        # under sigma=1.0; sigma=0.5 regularises harder while still allowing
        # meaningful team variation if it exists.
        sigma_team = pm.HalfNormal("sigma_team", sigma=0.5)
        alpha_team_z = pm.Normal("alpha_team_z", mu=0.0, sigma=1.0, dims="team")
        alpha_team = pm.Deterministic(  # noqa: F841
            "alpha_team", alpha_team_z * sigma_team, dims="team"
        )
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + alpha_team[team_idx] + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            random_seed=seed,
            progressbar=False,
            target_accept=target_accept,
        )

    return V3FitResult(
        trace=trace,
        feature_cols=feature_cols,
        feature_means=means,
        feature_stds=stds,
        y_mean=y_mean,
        y_std=y_std,
    )


def predict_multilevel(fit: V3FitResult, df: pd.DataFrame) -> np.ndarray:
    """Posterior-predictive samples for a held-out set. Shape (n_rows, n_samples).

    Teams unseen in training fall back to the population intercept (alpha0)
    because partial pooling shrinks them to zero.  Unseen teams get
    alpha_team = 0 implicitly.
    """
    cols = list(fit.feature_cols)
    x_test = ((df[cols] - fit.feature_means) / fit.feature_stds).to_numpy(dtype=float)
    post = fit.trace.posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    sigma_s = post["sigma"].values.reshape(n_samples)
    beta_s = post["beta"].values.reshape(n_samples, len(cols))
    teams = list(post.coords["team"].values)
    team_to_idx = {t: i for i, t in enumerate(teams)}
    alpha_team_s = post["alpha_team"].values.reshape(n_samples, len(teams))

    n_test = len(df)
    out = np.zeros((n_test, n_samples))
    for i in range(n_test):
        t = df["receiver_bref"].iloc[i]
        tidx = team_to_idx.get(t, None)
        team_effect = alpha_team_s[:, tidx] if tidx is not None else 0.0
        mu = alpha0_s + team_effect + beta_s @ x_test[i]
        rng = np.random.default_rng(seed=137 + i)
        noise = rng.normal(0.0, sigma_s)
        out[i] = (mu + noise) * fit.y_std + fit.y_mean
    return out


def backtest_outcome_v3_multilevel(
    outcome: str,
    train_end_season: int = 2020,
    test_end_season: int = 2024,
    feature_cols: tuple[str, ...] | None = None,
    minimum_features_present: int | None = None,
    combined: pd.DataFrame | None = None,
    meaningful_trades_only: bool = False,
    draws: int = 1500,
    tune: int = 2000,
    chains: int = 4,
) -> V3BacktestResult:
    """Run V3-multilevel train/test backtest for one outcome.

    Mirrors ``backtest_outcome_v3`` exactly, substituting
    ``fit_v3_multilevel`` and ``predict_multilevel``.
    """
    cols = feature_cols if feature_cols is not None else V3_OUTCOME_FEATURES[outcome]
    if combined is None:
        combined = assemble_v3_combined()
    train, test = _split_and_impute(
        outcome,
        cols,
        train_end_season,
        test_end_season,
        minimum_features_present,
        combined=combined,
        meaningful_trades_only=meaningful_trades_only,
    )
    if len(train) < 50:
        msg = f"V3-multilevel outcome={outcome}: only {len(train)} train rows after filtering"
        raise ValueError(msg)

    fit = fit_v3_multilevel(train, outcome, cols, draws=draws, tune=tune, chains=chains)
    test_pred = predict_multilevel(fit, test)
    y_test = test[outcome].to_numpy(dtype=float)

    mean_pred = test_pred.mean(axis=1)
    mae = float(np.mean(np.abs(mean_pred - y_test)))
    crps = _crps_empirical(y_test, test_pred)
    p05 = np.percentile(test_pred, 5, axis=1)
    p95 = np.percentile(test_pred, 95, axis=1)
    cov = float(((y_test >= p05) & (y_test <= p95)).mean())

    test_predictions = test[["trade_event_id", "receiver_bref", "trade_season"]].copy()
    test_predictions["y_true"] = y_test
    test_predictions["y_pred_mean"] = mean_pred
    test_predictions["y_pred_p05"] = p05
    test_predictions["y_pred_p95"] = p95

    return V3BacktestResult(
        outcome=outcome,
        fit=fit,
        train_n=len(train),
        test_n=len(test),
        test_mae=mae,
        test_crps=crps,
        coverage_90=cov,
        credible_features=coefficient_summary(fit),
        test_predictions=test_predictions,
    )
