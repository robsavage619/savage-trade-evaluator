"""V2 PyMC multilevel model with (team, regime) nested clusters.

Per D-28:
    alpha[regime] ~ Normal(alpha[team], tau_regime)
    alpha[team]   ~ Normal(0, tau_team)
    y_hat = alpha[regime[i]] + beta · features[i]
    y ~ Normal(y_hat, sigma)

The two-level pooling lets us learn each team's baseline (alpha[team]) while
allowing GM-regime-specific shifts within that team. Empty regimes (pre-1990
fallback) inherit the team's baseline directly with no within-team shift.

Returns a posterior trace plus the regime + team encoding tables so callers
can map predictions back to teams.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pymc as pm


@dataclass(frozen=True, slots=True)
class V2FitResult:
    """Container for a V2 multilevel fit."""

    trace: object  # arviz InferenceData
    feature_cols: tuple[str, ...]
    teams: tuple[str, ...]
    regimes: tuple[str, ...]
    regime_to_team: dict[str, str]
    feature_means: pd.Series
    feature_stds: pd.Series
    y_mean: float
    y_std: float


def _standardize(
    df: pd.DataFrame, feature_cols: tuple[str, ...]
) -> tuple[np.ndarray, pd.Series, pd.Series]:
    """Z-score each feature column. Returns (matrix, means, stds)."""
    means = df[list(feature_cols)].mean()
    stds = df[list(feature_cols)].std().replace(0, 1.0)
    x = ((df[list(feature_cols)] - means) / stds).to_numpy(dtype=float)
    return x, means, stds


def fit_multilevel_v2(
    df: pd.DataFrame,
    outcome_col: str,
    feature_cols: tuple[str, ...],
    regime_col: str = "regime_id",
    team_col: str = "receiver_bref",
    draws: int = 1500,
    tune: int = 2000,
    chains: int = 4,
    seed: int = 137,
    target_accept: float = 0.97,
) -> V2FitResult:
    """Fit the V2 multilevel model on one outcome.

    Args:
        df: Combined feature + outcome DataFrame, complete cases only.
        outcome_col: Column name of the target (e.g. ``xwoba_delta``).
        feature_cols: Standardized predictor columns.
        regime_col: Column name for the regime cluster identifier.
        team_col: Column name for the team identifier (parent cluster).
        draws / tune / chains / seed / target_accept: PyMC sample kwargs.

    Returns:
        V2FitResult with trace + encoding tables for prediction.
    """
    teams = tuple(sorted(df[team_col].unique()))
    regimes = tuple(sorted(df[regime_col].unique()))
    team_to_idx = {t: i for i, t in enumerate(teams)}
    regime_to_idx = {r: i for i, r in enumerate(regimes)}
    regime_to_team = {r: df[df[regime_col] == r][team_col].iloc[0] for r in regimes}
    regime_team_idx = np.array([team_to_idx[regime_to_team[r]] for r in regimes])

    x, feature_means, feature_stds = _standardize(df, feature_cols)
    y = df[outcome_col].to_numpy(dtype=float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    regime_idx = np.array([regime_to_idx[r] for r in df[regime_col]])

    coords = {
        "team": list(teams),
        "regime": list(regimes),
        "feature": list(feature_cols),
    }
    with pm.Model(coords=coords):
        # Population intercept (in z-units)
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        # Team-level deviations from alpha0
        tau_team = pm.HalfNormal("tau_team", sigma=1.0)
        alpha_team = pm.Normal("alpha_team", mu=0.0, sigma=tau_team, dims="team")
        # Regime-level deviations from their parent team
        tau_regime = pm.HalfNormal("tau_regime", sigma=0.5)
        alpha_regime_dev = pm.Normal("alpha_regime_dev", mu=0.0, sigma=tau_regime, dims="regime")
        # Full regime intercept: team baseline + regime shift
        alpha_regime = pm.Deterministic(
            "alpha_regime",
            alpha_team[regime_team_idx] + alpha_regime_dev,
            dims="regime",
        )
        # Feature coefficients
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, dims="feature")
        # Observation noise
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + alpha_regime[regime_idx] + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)

        trace = pm.sample(
            draws=draws,
            tune=tune,
            chains=chains,
            random_seed=seed,
            progressbar=False,
            target_accept=target_accept,
        )

    return V2FitResult(
        trace=trace,
        feature_cols=feature_cols,
        teams=teams,
        regimes=regimes,
        regime_to_team=regime_to_team,
        feature_means=feature_means,
        feature_stds=feature_stds,
        y_mean=y_mean,
        y_std=y_std,
    )


def coefficient_summary(fit: V2FitResult) -> pd.DataFrame:
    """Per-feature posterior summary with credibility flag (D-26 threshold)."""
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
        rows.append(
            {
                "feature": name,
                "mean_beta": mean,
                "p05": p05,
                "p95": p95,
                "directional_mass": mass,
                "ci_excludes_zero": ci_excludes_zero,
                "credible": credible,
            }
        )
    return (
        pd.DataFrame(rows).sort_values("directional_mass", ascending=False).reset_index(drop=True)
    )
