"""V3 single-level Bayesian regression — the post-R-33/34/35 architecture.

R-33: regime nesting adds zero signal over team-only pooling.
R-34: team pooling adds zero signal over flat pop-intercept regression.
R-35: team pooling adds zero even without feature collinearity.

Conclusion: drop the multilevel scaffolding. Single-level Bayesian
regression with per-outcome feature selection (D-27) is the architecture.

Pieces shared with V2 (no need to re-implement):
- ``v2.features.build_feature_matrix`` — feature DataFrame
- ``v2.outcomes.build_outcomes`` — 4-outcome target matrix
- ``v2.backtest.assemble_combined`` — the merged feature+outcome matrix
- ``v2.backtest._crps_empirical`` — CRPS scoring

Per-outcome feature subset (set empirically by R-35):
- xwoba_delta, kpct_delta: player-only (8 features) — small-n outcomes
  overfit on team-aggregate features
- war_delta, dollar_surplus: all features (16) — large-n outcomes get
  signal from team-aggregate features
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd  # noqa: E402
import pymc as pm

from savage_trade_evaluator.modeling.v2.backtest import (
    _crps_empirical,
    assemble_combined,
)
from savage_trade_evaluator.modeling.v2.features import (
    ACQUIRED_PLAYER_FEATURES,
    ALL_FEATURES,
)
from savage_trade_evaluator.modeling.v2.outcomes import build_outcomes, build_outcomes_windowed

# Q-07: war_delta skips the transition year (T+1) — 30% MAE improvement.
# Q-02: extending to T+5 adds further credible features (11 vs 6 at T+1..T+3).
# Combined T+2..T+5 is the V3 default for war_delta.  Dollar_surplus keeps
# T+1..T+3 because cap obligations in year 1 are real.
V3_WAR_WINDOW: tuple[int, int] = (2, 5)


def _build_v3_outcomes() -> pd.DataFrame:
    """Build outcomes with per-outcome window choices (D-Q02/Q07 empirical findings).

    war_delta    → T+2..T+5  (skip transition year, extend to 5yr)
    dollar_surplus → T+1..T+3 (standard; shifting hurts it per Q-07)
    xwoba_delta, kpct_delta → from standard build_outcomes()
    """
    import pandas as pd

    # Standard outcomes for xwoba_delta + kpct_delta + dollar_surplus
    std = build_outcomes()
    # war_delta from T+2..T+5
    war_windowed = build_outcomes_windowed(
        war_window_start=V3_WAR_WINDOW[0],
        war_window_end=V3_WAR_WINDOW[1],
    )[["trade_event_id", "receiver_bref", "trade_season", "war_delta"]]
    merged = std.drop(columns=["war_delta"]).merge(
        war_windowed, on=["trade_event_id", "receiver_bref", "trade_season"], how="left"
    )
    return merged


def assemble_v3_combined() -> pd.DataFrame:
    """Feature + outcome matrix with V3-specific window choices for war_delta."""
    return assemble_combined(outcomes_df=_build_v3_outcomes())

# Per-outcome feature subsets per R-35.
V3_OUTCOME_FEATURES: dict[str, tuple[str, ...]] = {
    # R-53/R-55: component-outcome-credible team features wired per D-33/D-35.
    "xwoba_delta": ACQUIRED_PLAYER_FEATURES + (
        "receiver_tech_adoption_lead_years",
        "receiver_platoon_woba_diff",      # D-35/R-55: β=+0.099, mass=97%
    ),
    "kpct_delta": ACQUIRED_PLAYER_FEATURES + (
        "receiver_alumni_network_score",
        "receiver_tech_adoption_lead_years",
    ),
    "war_delta": ALL_FEATURES,
    "dollar_surplus": ALL_FEATURES,
}


@dataclass(frozen=True, slots=True)
class V3FitResult:
    """Container for one V3 fit."""

    trace: object  # arviz InferenceData
    feature_cols: tuple[str, ...]
    feature_means: pd.Series
    feature_stds: pd.Series
    y_mean: float
    y_std: float


@dataclass(frozen=True, slots=True)
class V3BacktestResult:
    """Container for one V3 outcome's backtest."""

    outcome: str
    fit: V3FitResult
    train_n: int
    test_n: int
    test_mae: float
    test_crps: float
    coverage_90: float
    credible_features: pd.DataFrame
    test_predictions: pd.DataFrame


def _split_and_impute(
    outcome: str,
    feature_cols: tuple[str, ...],
    train_end_season: int = 2020,
    test_end_season: int = 2024,
    minimum_features_present: int | None = None,
    combined: pd.DataFrame | None = None,
    meaningful_trades_only: bool = False,
    train_start_season: int = 2010,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if combined is None:
        combined = assemble_v3_combined()
    if meaningful_trades_only:
        # Q-01: restrict to trades where at least one acquired player had ≥2 WAR
        # in T-1. Uses receiver_acquired_player_quality as an ordinal proxy —
        # the actual war_t_minus_1 filter requires a separate join.
        combined = combined[combined["receiver_acquired_player_quality"].notna()
                            & (combined["receiver_acquired_player_quality"] >= 1.0)].copy()
    combined = combined[combined[outcome].notna()].copy()
    # Default 5 matches V2's smoke-test convention; loose enough that
    # large-feature-set outcomes (war / dollar) keep ~3600 train rows.
    min_present = minimum_features_present if minimum_features_present is not None else 5
    present = combined[list(feature_cols)].notna().sum(axis=1)
    complete = combined[present >= min_present].copy()
    for c in feature_cols:
        complete[c] = complete[c].astype("float64")
        complete[c] = complete[c].fillna(complete[c].mean())
    train = complete[
        (complete["trade_season"] >= train_start_season)
        & (complete["trade_season"] <= train_end_season)
    ].reset_index(drop=True)
    test = complete[
        (complete["trade_season"] > train_end_season)
        & (complete["trade_season"] <= test_end_season)
    ].reset_index(drop=True)
    return train, test


def fit_v3(
    train: pd.DataFrame,
    outcome: str,
    feature_cols: tuple[str, ...],
    draws: int = 1500,
    tune: int = 2000,
    chains: int = 4,
    seed: int = 137,
    target_accept: float = 0.99,
    sigma_prior: float = 1.0,
) -> V3FitResult:
    """Fit V3 (single-level Bayesian regression) on one outcome."""
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
        sigma = pm.HalfNormal("sigma", sigma=sigma_prior)
        mu = alpha0 + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=draws, tune=tune, chains=chains, random_seed=seed,
            progressbar=False, target_accept=target_accept,
        )
    return V3FitResult(
        trace=trace, feature_cols=feature_cols,
        feature_means=means, feature_stds=stds,
        y_mean=y_mean, y_std=y_std,
    )


def predict(
    fit: V3FitResult,
    df: pd.DataFrame,
    era_cutoff: int | None = None,
) -> np.ndarray:
    """Posterior-predictive samples for a held-out set. Shape (n_rows, n_samples).

    Args:
        fit: Fitted V3 result (flat or heteroscedastic).
        df: Test DataFrame. Must contain ``trade_season`` if ``era_cutoff`` is set.
        era_cutoff: When set, compute per-row post_era from df["trade_season"] and
            use it to reconstruct the heteroscedastic sigma. Pass None (default)
            for flat-sigma fits.
    """
    cols = list(fit.feature_cols)
    x_test = ((df[cols] - fit.feature_means) / fit.feature_stds).to_numpy(dtype=float)
    post = fit.trace.posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    beta_s = post["beta"].values.reshape(n_samples, len(cols))
    n_test = len(df)
    out = np.zeros((n_test, n_samples))

    heteroscedastic = era_cutoff is not None and "log_sigma_base" in post
    if heteroscedastic:
        log_sigma_base_s = post["log_sigma_base"].values.reshape(n_samples)
        beta_sigma_era_s = post["beta_sigma_era"].values.reshape(n_samples)
        post_era_vec = (df["trade_season"].to_numpy() >= era_cutoff).astype(float)
    else:
        sigma_s = post["sigma"].values.reshape(n_samples)

    for i in range(n_test):
        mu = alpha0_s + beta_s @ x_test[i]
        rng = np.random.default_rng(seed=137 + i)
        if heteroscedastic:
            sigma_i = np.exp(log_sigma_base_s + beta_sigma_era_s * post_era_vec[i])
            noise = rng.normal(0.0, sigma_i)
        else:
            noise = rng.normal(0.0, sigma_s)
        out[i] = (mu + noise) * fit.y_std + fit.y_mean
    return out


def coefficient_summary(fit: V3FitResult) -> pd.DataFrame:
    """Per-feature posterior summary + D-26 credibility flag."""
    beta = fit.trace.posterior["beta"].values.reshape(-1, len(fit.feature_cols))
    rows = []
    for i, name in enumerate(fit.feature_cols):
        v = beta[:, i]
        mean = float(v.mean())
        p05 = float(np.percentile(v, 5))
        p95 = float(np.percentile(v, 95))
        mass_pos = float((v > 0).mean())
        mass = max(mass_pos, 1 - mass_pos)
        ci_excludes_zero = (p05 > 0 and p95 > 0) or (p05 < 0 and p95 < 0)
        credible = ci_excludes_zero and mass >= 0.95
        rows.append({
            "feature": name, "mean_beta": mean, "p05": p05, "p95": p95,
            "directional_mass": mass, "ci_excludes_zero": ci_excludes_zero,
            "credible": credible,
        })
    return (
        pd.DataFrame(rows).sort_values("directional_mass", ascending=False).reset_index(drop=True)
    )


def backtest_outcome_v3(
    outcome: str,
    train_end_season: int = 2020,
    test_end_season: int = 2024,
    feature_cols: tuple[str, ...] | None = None,
    minimum_features_present: int | None = None,
    combined: pd.DataFrame | None = None,
    meaningful_trades_only: bool = False,
    sigma_prior: float = 1.0,
    train_start_season: int = 2010,
) -> V3BacktestResult:
    """Run V3 train/test backtest for one outcome."""
    cols = feature_cols if feature_cols is not None else V3_OUTCOME_FEATURES[outcome]
    train, test = _split_and_impute(
        outcome, cols, train_end_season, test_end_season, minimum_features_present,
        combined=combined, meaningful_trades_only=meaningful_trades_only,
        train_start_season=train_start_season,
    )
    if len(train) < 50:
        msg = (
            f"V3 outcome={outcome}: only {len(train)} train rows after filtering"
        )
        raise ValueError(msg)

    fit = fit_v3(train, outcome, cols, sigma_prior=sigma_prior)
    test_pred = predict(fit, test)
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
        outcome=outcome, fit=fit,
        train_n=len(train), test_n=len(test),
        test_mae=mae, test_crps=crps, coverage_90=cov,
        credible_features=coefficient_summary(fit),
        test_predictions=test_predictions,
    )


def fit_v3_heteroscedastic(
    train: pd.DataFrame,
    outcome: str,
    feature_cols: tuple[str, ...],
    era_cutoff: int = 2021,
    draws: int = 1500,
    tune: int = 2000,
    chains: int = 4,
    seed: int = 137,
    target_accept: float = 0.99,
) -> V3FitResult:
    """Fit V3 with era-heteroscedastic sigma on one outcome.

    sigma = exp(log_sigma_base + beta_sigma_era * post_era)

    where post_era = 1 if trade_season >= era_cutoff else 0.
    Allows the model to learn that post-rule-change era has lower residual variance.
    """
    means = train[list(feature_cols)].mean()
    stds = train[list(feature_cols)].std().replace(0, 1.0)
    x = ((train[list(feature_cols)] - means) / stds).to_numpy(dtype=float)
    y = train[outcome].to_numpy(dtype=float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    post_era = (train["trade_season"].to_numpy() >= era_cutoff).astype(float)

    coords = {"feature": list(feature_cols)}
    with pm.Model(coords=coords):
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        log_sigma_base = pm.Normal("log_sigma_base", mu=0.0, sigma=1.0)
        beta_sigma_era = pm.Normal("beta_sigma_era", mu=0.0, sigma=1.0)
        sigma = pm.math.exp(log_sigma_base + beta_sigma_era * post_era)
        mu = alpha0 + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            draws=draws, tune=tune, chains=chains, random_seed=seed,
            progressbar=False, target_accept=target_accept,
        )
    return V3FitResult(
        trace=trace, feature_cols=feature_cols,
        feature_means=means, feature_stds=stds,
        y_mean=y_mean, y_std=y_std,
    )


def backtest_outcome_v3_heteroscedastic(
    outcome: str,
    train_end_season: int = 2020,
    test_end_season: int = 2024,
    feature_cols: tuple[str, ...] | None = None,
    minimum_features_present: int | None = None,
    combined: pd.DataFrame | None = None,
    meaningful_trades_only: bool = False,
    era_cutoff: int = 2021,
) -> V3BacktestResult:
    """Run V3 heteroscedastic-sigma train/test backtest for one outcome."""
    cols = feature_cols if feature_cols is not None else V3_OUTCOME_FEATURES[outcome]
    train, test = _split_and_impute(
        outcome, cols, train_end_season, test_end_season, minimum_features_present,
        combined=combined, meaningful_trades_only=meaningful_trades_only,
    )
    if len(train) < 50:
        msg = f"V3 outcome={outcome}: only {len(train)} train rows after filtering"
        raise ValueError(msg)

    fit = fit_v3_heteroscedastic(train, outcome, cols, era_cutoff=era_cutoff)
    test_pred = predict(fit, test, era_cutoff=era_cutoff)
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
        outcome=outcome, fit=fit,
        train_n=len(train), test_n=len(test),
        test_mae=mae, test_crps=crps, coverage_90=cov,
        credible_features=coefficient_summary(fit),
        test_predictions=test_predictions,
    )


def print_backtest_report(result: V3BacktestResult) -> None:
    """Plain-English summary of one V3 backtest outcome."""
    print("=" * 88)
    print(f"V3 BACKTEST: outcome={result.outcome}  ({len(result.fit.feature_cols)} features)")
    print("=" * 88)
    print(f"  Train n: {result.train_n}, Test n: {result.test_n}")
    print(f"  Test MAE:    {result.test_mae:.4f}")
    print(f"  Test CRPS:   {result.test_crps:.4f}")
    print(f"  90% coverage: {result.coverage_90:.1%}  (target: 90%)")
    print()
    print("CREDIBLE FEATURES (D-26: 90% CI excludes zero AND mass >= 95%):")
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
