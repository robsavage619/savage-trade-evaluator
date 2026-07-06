"""Shared test fixtures."""

from __future__ import annotations

import arviz as az
import numpy as np
import pandas as pd
import pytest

from savage_trade_evaluator.modeling.v3 import V3FitResult


@pytest.fixture()
def synthetic_fit() -> V3FitResult:
    """V3FitResult with 3 known features and constant posterior draws.

    Designed so attribution math is assertable without running MCMC.

    Features: feat_a (credible, positive), feat_b (credible, negative), feat_c (not credible).
    alpha0 = 0.1 (z-space), beta = [0.4, -0.2, 0.0], sigma = 0.5, nu_minus_two = 3.0.
    y_mean = 1.0, y_std = 2.0.
    """
    features = ("feat_a", "feat_b", "feat_c")
    n_chains, n_draws = 2, 100

    # Constant draws so posterior mean = the known value.
    alpha0 = np.full((n_chains, n_draws), 0.1)
    # beta shape: (n_chains, n_draws, n_features)
    beta_vals = np.array([0.4, -0.2, 0.0])
    beta = np.broadcast_to(beta_vals, (n_chains, n_draws, len(features))).copy()
    sigma = np.full((n_chains, n_draws), 0.5)
    nu_minus_two = np.full((n_chains, n_draws), 3.0)

    trace = az.from_dict(
        {
            "posterior": {
                "alpha0": alpha0,
                "beta": beta,
                "sigma": sigma,
                "nu_minus_two": nu_minus_two,
            }
        },
        coords={"feature": list(features)},
        dims={"beta": ["feature"]},
    )

    means = pd.Series({"feat_a": 0.0, "feat_b": 0.0, "feat_c": 0.0})
    stds = pd.Series({"feat_a": 1.0, "feat_b": 1.0, "feat_c": 1.0})
    clip_lo = means - 5.0 * stds
    clip_hi = means + 5.0 * stds

    return V3FitResult(
        trace=trace,
        feature_cols=features,
        feature_means=means,
        feature_stds=stds,
        feature_clip_lo=clip_lo,
        feature_clip_hi=clip_hi,
        y_mean=1.0,
        y_std=2.0,
    )
