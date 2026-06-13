from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import norm

from savage_trade_evaluator.modeling.metrics import crps_empirical


def _crps_analytic_normal(mu: float, sigma: float, y: float) -> float:
    """Closed-form CRPS for N(mu, sigma) predictive vs scalar observation y.

    CRPS(N(m,s), y) = s*[ z*(2*Phi(z)-1) + 2*phi(z) - 1/sqrt(pi) ]  where z=(y-m)/s.
    """
    z = (y - mu) / sigma
    return sigma * (z * (2 * norm.cdf(z) - 1) + 2 * norm.pdf(z) - 1 / np.sqrt(np.pi))


def _crps_pairwise(observed: np.ndarray, samples: np.ndarray) -> float:
    """O(m²) reference implementation (matches bayesian.py)."""
    n, _ = samples.shape
    out = np.empty(n)
    for i in range(n):
        s = samples[i]
        term1 = float(np.mean(np.abs(s - observed[i])))
        diffs = np.abs(s[:, None] - s[None, :])
        term2 = 0.5 * float(diffs.mean())
        out[i] = term1 - term2
    return float(out.mean())


@pytest.mark.parametrize("m", [30, 1000, 6000])
def test_crps_matches_pairwise(m: int) -> None:
    rng = np.random.default_rng(42)
    n = 20
    mu, sigma = 0.0, 1.0
    observed = rng.normal(mu, sigma, n)
    samples = rng.normal(mu, sigma, (n, m))
    canonical = crps_empirical(observed, samples)
    reference = _crps_pairwise(observed, samples)
    np.testing.assert_allclose(canonical, reference, rtol=1e-6)


@pytest.mark.parametrize("m", [30, 1000, 6000])
def test_crps_matches_analytic_normal(m: int) -> None:
    rng = np.random.default_rng(7)
    n = 50
    mu, sigma = 0.0, 1.0
    observed = rng.normal(mu, sigma, n)
    samples = rng.normal(mu, sigma, (n, m))
    analytic = float(np.mean([_crps_analytic_normal(mu, sigma, y) for y in observed]))
    canonical = crps_empirical(observed, samples)
    # At m=30 Monte Carlo noise is higher; m=6000 should be very tight.
    tol = 0.05 if m == 30 else 0.01
    np.testing.assert_allclose(canonical, analytic, atol=tol)
