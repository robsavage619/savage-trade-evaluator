"""Unit tests for the arb/control primitives of value_player (pure, no DB)."""

from __future__ import annotations

import pytest

from savage_trade_evaluator.modeling.value_player import (
    MLB_MIN,
    _project_salary,
    aging_delta,
    infer_player_type,
    parse_arb_class,
)


def test_parse_arb_class() -> None:
    assert parse_arb_class(None) == "fa"
    assert parse_arb_class("Pre-Arbitration") == "pre-arb"
    assert parse_arb_class("Arbitration 1") == "arb1"
    assert parse_arb_class("Arbitration 3") == "arb3"
    assert parse_arb_class("Free Agent") == "fa"


def test_infer_player_type() -> None:
    assert infer_player_type("SP", is_reliever=False) == "starter"
    assert infer_player_type("RP", is_reliever=True) == "reliever"
    assert infer_player_type("SS", is_reliever=False) == "batter"
    # A nominal "P" pitching in relief is priced as a reliever.
    assert infer_player_type("P", is_reliever=True) == "reliever"


def test_aging_curve_shape() -> None:
    assert aging_delta(22) > 0  # improving
    assert aging_delta(27) == 0.0  # peak
    assert aging_delta(31) < 0  # declining
    assert aging_delta(35) < aging_delta(31)  # accelerating


def test_pre_arb_salary_is_the_minimum() -> None:
    assert _project_salary("pre-arb", 4.0, "starter", "SP", None) == pytest.approx(MLB_MIN)


def test_arb_salary_scales_with_war_and_ramps() -> None:
    arb1 = _project_salary("arb1", 4.0, "starter", "SP", None)
    arb3 = _project_salary("arb3", 4.0, "starter", "SP", None)
    assert arb3 > arb1 > MLB_MIN  # arb ramp: later years pay more


def test_fa_salary_uses_known_cap_hit() -> None:
    assert _project_salary("fa", 2.0, "batter", "1B", 15_000_000) == pytest.approx(15_000_000)
