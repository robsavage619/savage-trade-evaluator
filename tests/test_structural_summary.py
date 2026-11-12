from __future__ import annotations

import numpy as np

from savage_trade_evaluator.modeling.structural import (
    difference_atoms,
    summarize_atoms,
)


def test_summarize_atoms_point_mass_and_quantiles() -> None:
    # 40% at zero, then 60% spread evenly over 1..6
    values = np.array([0.0, 1, 2, 3, 4, 5, 6])
    weights = np.array([0.4] + [0.1] * 6)
    s = summarize_atoms(values, weights)
    assert abs(s["mean"] - (0.1 * 21)) < 1e-12
    assert s["p5"] == 0.0 and s["median"] == 1.0 and s["p95"] == 6.0
    assert abs(s["p_positive"] - 0.6) < 1e-12


def test_difference_of_identical_sides_is_centered_on_zero() -> None:
    values = np.array([0.0, 1, 2, 3])
    weights = np.array([0.25, 0.25, 0.25, 0.25])
    s = summarize_atoms(*difference_atoms((values, weights), (values, weights)))
    assert abs(s["mean"]) < 1e-12 and s["median"] == 0.0
    assert abs(s["p_positive"] - 6 / 16) < 1e-12  # P(A > B) = (1 - P(tie)) / 2
