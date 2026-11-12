from __future__ import annotations

import numpy as np


def crps_empirical(observed: np.ndarray, samples: np.ndarray) -> float:
    """Canonical CRPS: E|X-y| - 0.5*E|X-X'|, O(m log m) via gap-weighted Gini.

    Args:
        observed: 1-D array of realized values, shape (n,).
        samples: 2-D array of posterior predictive draws, shape (n, m).

    Returns:
        Mean CRPS across the n observations.
    """
    _n, m = samples.shape
    term1 = np.mean(np.abs(samples - observed[:, None]))

    # E|X-X'| via the gap-weighted formula:
    #   Σ_k k·(m-k)·d_k  (k = 1..m-1, d_k = gap between kth and (k+1)th sorted sample)
    # normalised by m^2 to match the pairwise-mean estimator (sum / m^2 pairs counted
    # with repetition), consistent with the O(m²) reference in bayesian.py.
    sorted_s = np.sort(samples, axis=1)  # (n, m)
    diffs = np.diff(sorted_s, axis=1)  # (n, m-1)
    k = np.arange(1, m, dtype=np.float64)  # [1, 2, ..., m-1]
    weights = k * (m - k)  # (m-1,)
    spread = np.sum(diffs * weights[None, :], axis=1)  # (n,)
    term2 = 0.5 * np.mean(2.0 * spread / m**2)

    return float(term1 - term2)


def favoured_side_score(
    pred_margin: np.ndarray, real_margin: np.ndarray
) -> tuple[float, float, int]:
    """Decision-level score for two-sided trades.

    A margin is side A minus side B. The favoured side is the sign of the
    predicted margin. Trades with no predicted or no realized winner are dropped.

    Args:
        pred_margin: Predicted value margin per trade, shape (n,).
        real_margin: Realized value margin per trade, shape (n,).

    Returns:
        (win rate of the favoured side, mean realized margin gained by taking
        the favoured side, number of decisive trades).
    """
    decisive = (pred_margin != 0) & (real_margin != 0)
    n = int(decisive.sum())
    if n == 0:
        return float("nan"), float("nan"), 0
    gained = np.sign(pred_margin[decisive]) * real_margin[decisive]
    return float(np.mean(gained > 0)), float(np.mean(gained)), n
