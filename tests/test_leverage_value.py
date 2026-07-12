"""Unit tests for leverage-aware reliever valuation (pure functions, no DB)."""

from __future__ import annotations

import pytest

from savage_trade_evaluator.modeling.leverage_value import (
    _MAX_WEIGHT,
    _MIN_WEIGHT,
    leverage_adjusted_war,
    leverage_weight,
)


def test_starter_never_adjusted() -> None:
    # Starters enter at leverage 1.0 by construction — no correction regardless of gmLI.
    assert leverage_weight(0.75, is_reliever=False) == 1.0
    assert leverage_weight(1.63, is_reliever=False) == 1.0
    assert leverage_adjusted_war(2.2, 0.78, is_reliever=False) == pytest.approx(2.2)


def test_reliever_weight_is_leverage_index_correction() -> None:
    # (1 + gmLI) / 2 for relievers.
    assert leverage_weight(1.0, is_reliever=True) == pytest.approx(1.0)
    assert leverage_weight(1.35, is_reliever=True) == pytest.approx(1.175)  # league-avg reliever
    assert leverage_weight(1.63, is_reliever=True) == pytest.approx(1.315)  # elite closer (Miller)


def test_elite_closer_credited_above_league_reliever() -> None:
    # Miller's high-leverage usage must value his WAR above an average reliever's.
    miller = leverage_adjusted_war(2.0, 1.63, is_reliever=True)
    league = leverage_adjusted_war(2.0, 1.35, is_reliever=True)
    assert miller > league > 2.0


def test_weight_is_monotonic_in_leverage() -> None:
    lows = [leverage_weight(x, is_reliever=True) for x in (0.8, 1.0, 1.2, 1.4, 1.6)]
    assert lows == sorted(lows)


def test_weight_bounded_at_extremes() -> None:
    assert leverage_weight(-5.0, is_reliever=True) == _MIN_WEIGHT
    assert leverage_weight(10.0, is_reliever=True) == _MAX_WEIGHT
