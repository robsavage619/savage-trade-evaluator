"""Hermetic tests for org-quality franchise aliasing and credit aggregation."""

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.analysis.org_quality import (
    CURRENT_30_FRANCHISES,
    DRAFT_NAME_TO_BREF,
    FRANCHISE_ALIASES,
    FULL_NAMES,
    _alias,
    _dev_credit,
    _intl_credit,
)


def test_alias_maps_historical_codes() -> None:
    assert _alias("TBD") == "TBR"
    assert _alias("MON") == "WSN"
    assert _alias("HOU") == "HOU"
    assert _alias(None) is None


def test_alias_targets_are_current_franchises() -> None:
    assert set(FRANCHISE_ALIASES.values()) <= CURRENT_30_FRANCHISES
    assert set(DRAFT_NAME_TO_BREF.values()) <= CURRENT_30_FRANCHISES
    assert set(FULL_NAMES) == CURRENT_30_FRANCHISES


def test_dev_credit_filters_and_aggregates() -> None:
    df = pd.DataFrame(
        {
            "mlb_id": [1, 2, 3, 4, 5, 6],
            "first_mlb_team": ["HOU", "HOU", "XYZ", None, "BOS", "HOU"],
            "career_war": [10.0, 5.0, 3.0, 2.0, 2.0, 4.0],
            "first_year": [2000, 1980, 2000, 2000, 1995, 2010],
        }
    )
    out = _dev_credit(df, since_year=1990)
    assert len(out) == 2
    assert out.loc["HOU", "n_mlb_debutees"] == 2
    assert out.loc["HOU", "dev_war"] == 14.0
    assert out.loc["BOS", "dev_war"] == 2.0
    assert out.index[0] == "HOU"  # sorted by dev_war desc


def test_intl_credit_excludes_drafted_and_pre_1995() -> None:
    df = pd.DataFrame(
        {
            "mlb_id": [1, 2, 3],
            "first_mlb_team": ["HOU", "HOU", "HOU"],
            "career_war": [4.0, 6.0, 1.0],
            "first_year": [2000, 2000, 1994],
            "drafting_team_bref": [None, "HOU", None],
        }
    )
    out = _intl_credit(df)
    assert len(out) == 1
    assert out.loc["HOU", "n_intl"] == 1
    assert out.loc["HOU", "intl_war"] == 4.0
