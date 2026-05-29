"""Tests for role-adjusted value (no DB, pure linear algebra)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from savage_trade_evaluator.modeling import role_adjustment as ra


def test_role_adjust_removes_deployment_driven_component() -> None:
    """A value that is purely deployment + noise should residualize to ~the noise."""
    rng = np.random.default_rng(0)
    n = 400
    bf_delta = rng.normal(0, 50, n)
    lev_delta = rng.normal(0, 0.3, n)
    noise = rng.normal(0, 0.1, n)
    # war_delta is 0.01*bf + 1.5*lev + noise — deployment explains most of it.
    war_delta = 0.01 * bf_delta + 1.5 * lev_delta + noise
    frame = pd.DataFrame({"war_delta": war_delta, "bf_delta": bf_delta, "lev_delta": lev_delta})

    adjusted = ra.role_adjust(frame)

    # The adjusted series keeps the input scale (re-centered to the mean) ...
    assert adjusted.notna().all()
    assert abs(adjusted.mean() - war_delta.mean()) < 1e-9
    # ... and its correlation with the deployment drivers is ~0 (partialled out).
    assert abs(np.corrcoef(adjusted, bf_delta)[0, 1]) < 1e-6
    assert abs(np.corrcoef(adjusted, lev_delta)[0, 1]) < 1e-6
    # The residual should track the original noise far better than the raw value.
    assert np.corrcoef(adjusted, noise)[0, 1] > 0.9


def test_role_adjust_raises_on_missing_columns() -> None:
    frame = pd.DataFrame({"war_delta": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="missing required columns"):
        ra.role_adjust(frame)


def test_role_adjust_raises_on_too_few_rows() -> None:
    frame = pd.DataFrame({"war_delta": [1.0], "bf_delta": [2.0], "lev_delta": [0.1]})
    with pytest.raises(ValueError, match="need >=10"):
        ra.role_adjust(frame)
