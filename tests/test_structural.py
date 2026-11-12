from __future__ import annotations

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.structural import fit, held_seasons, predict


def test_held_seasons_splits_the_window_by_control() -> None:
    # July, last control year / December, rookie / February, free-agent-eligible veteran
    month, left, prior = np.array([7, 12, 2]), np.array([0.4, 0.0, 1.0]), np.array([5, 0, 6])
    ctrl, post = held_seasons(month, left, prior)
    assert np.allclose(ctrl, [0.4, 5.0, 0.0])
    assert np.allclose(post, [5.0, 0.0, 6.0])


def test_two_part_model_separates_zero_sides_from_producing_sides() -> None:
    rng = np.random.default_rng(0)
    n = 400
    held = np.concatenate([np.zeros(n // 2), rng.uniform(2, 10, n // 2)])
    x = pd.DataFrame({"held_ctrl_war": held, "n_no_mlb": (held == 0).astype(float)})
    y = np.where(held == 0, 0.0, held + rng.normal(0, 1, n))
    model = fit(x, y)
    test = pd.DataFrame({"held_ctrl_war": [0.0, 8.0], "n_no_mlb": [1.0, 0.0]})
    draws, expected = predict(model, test, np.random.default_rng(1), n_draws=500)
    assert draws.shape == (2, 500)
    assert np.mean(draws[0] == 0) > 0.9  # a side with nothing is forecast at zero
    assert abs(expected[1] - 8.0) < 1.0  # a side holding 8 WAR is forecast near 8
    assert expected[0] < 0.5
