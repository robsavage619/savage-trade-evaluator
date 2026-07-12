"""Unit tests for sample-size-aware WAR projection (pure functions, no DB)."""

from __future__ import annotations

import pytest

from savage_trade_evaluator.modeling.projection import (
    RELIEVER_BASELINE_WAR,
    STARTER_BASELINE_WAR,
    SeasonWar,
    playing_time_fraction,
    project_war,
)


def test_playing_time_fraction_by_role() -> None:
    assert playing_time_fraction(g=10, gs=10, is_reliever=False) == pytest.approx(10 / 32)
    assert playing_time_fraction(g=62, gs=0, is_reliever=True) == pytest.approx(1.0)


def test_empty_returns_baseline() -> None:
    assert project_war([], STARTER_BASELINE_WAR) == STARTER_BASELINE_WAR


def test_small_hot_sample_is_regressed_not_extrapolated() -> None:
    # 2.4 WAR in 10 starts is a ~7.6/season pace — projection must stay far below it.
    hot = [SeasonWar(2026, war=2.4, pt_fraction=10 / 32, is_reliever=False)]
    proj = project_war(hot, STARTER_BASELINE_WAR)
    assert proj < 4.0
    assert proj > STARTER_BASELINE_WAR  # a real hot streak still lifts above baseline


def test_full_repeated_seasons_dominate_baseline() -> None:
    # Three full ~3-WAR seasons project well above baseline (1.6), regressed toward
    # it by the calibrated shrinkage — ~2.5 at the default regression_pt=3.0.
    steady = [
        SeasonWar(2026, war=3.0, pt_fraction=1.0, is_reliever=False),
        SeasonWar(2025, war=3.0, pt_fraction=1.0, is_reliever=False),
        SeasonWar(2024, war=3.0, pt_fraction=1.0, is_reliever=False),
    ]
    proj = project_war(steady, STARTER_BASELINE_WAR)
    assert proj == pytest.approx(2.5, abs=0.25)
    assert proj - STARTER_BASELINE_WAR > 0.7  # stays much closer to 3 than to baseline


def test_partial_current_season_downweighted_vs_full_prior() -> None:
    # A weak partial current season shouldn't tank a strong recent full-season record.
    seasons = [
        SeasonWar(2026, war=0.5, pt_fraction=0.2, is_reliever=True),  # partial, weak
        SeasonWar(2025, war=2.4, pt_fraction=1.0, is_reliever=True),
        SeasonWar(2024, war=2.4, pt_fraction=1.0, is_reliever=True),
    ]
    proj = project_war(seasons, RELIEVER_BASELINE_WAR)
    assert proj > 1.6  # the two full 2.4 seasons carry more weight than the partial dip


def test_stronger_regression_pulls_harder() -> None:
    hot = [SeasonWar(2026, war=2.4, pt_fraction=10 / 32, is_reliever=False)]
    light = project_war(hot, STARTER_BASELINE_WAR, regression_pt=1.0)
    heavy = project_war(hot, STARTER_BASELINE_WAR, regression_pt=4.0)
    assert heavy < light
