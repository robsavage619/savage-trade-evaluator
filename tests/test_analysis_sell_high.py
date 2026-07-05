"""Hermetic tests for the sell-high vs system-tax decomposition."""

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.analysis.sell_high import (
    classify_mechanism,
    classify_player,
    regime_decomposition,
    sell_high_decomposition,
)


def _fixture_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "regime": ["R", "R", "R", "R", "S"],
            "pre": [3.0, 2.5, 0.5, 1.5, 1.0],
            "experience": [7.0, 8.0, 2.0, 5.0, 3.0],
            "delta": [-1.0, -2.0, 0.5, 0.0, 1.0],
        }
    )


def test_classify_vet_at_peak_boundary() -> None:
    assert classify_player(2.0, 6) == "VET-AT-PEAK"


def test_classify_young_prospect_boundary() -> None:
    assert classify_player(1.0, 4) == "YOUNG-PROSPECT"


def test_classify_middle() -> None:
    assert classify_player(1.5, 5) == "MIDDLE"
    assert classify_player(3.0, 5) == "MIDDLE"


def test_classify_missing_experience_is_middle() -> None:
    assert classify_player(3.0, None) == "MIDDLE"
    assert classify_player(3.0, float("nan")) == "MIDDLE"


def test_sell_high_decomposition_adds_bucket_column() -> None:
    out = sell_high_decomposition(_fixture_df())
    assert list(out["bucket"]) == [
        "VET-AT-PEAK",
        "VET-AT-PEAK",
        "YOUNG-PROSPECT",
        "MIDDLE",
        "YOUNG-PROSPECT",
    ]


def test_regime_decomposition_buckets() -> None:
    d = regime_decomposition(_fixture_df(), "R")
    assert d["VET-AT-PEAK"]["n"] == 2
    assert d["VET-AT-PEAK"]["mean_delta"] == -1.5
    assert d["YOUNG-PROSPECT"]["n"] == 1
    assert d["YOUNG-PROSPECT"]["mean_delta"] == 0.5
    assert d["MIDDLE"]["n"] == 1
    assert d["ALL"]["n"] == 4
    assert d["ALL"]["mean_delta"] == -0.625


def test_regime_decomposition_unknown_regime_is_empty() -> None:
    assert regime_decomposition(_fixture_df(), "NOPE") == {}


def test_mechanism_neutral() -> None:
    d = {"ALL": {"mean_delta": 0.0}, "VET-AT-PEAK": {}, "YOUNG-PROSPECT": {}}
    assert classify_mechanism(d) == "neutral"


def test_mechanism_sell_high() -> None:
    d = {
        "ALL": {"mean_delta": -0.5},
        "VET-AT-PEAK": {"n": 10, "mean_delta": -1.0},
        "YOUNG-PROSPECT": {"n": 10, "mean_delta": -0.2},
    }
    assert classify_mechanism(d) == "negative via SELL-HIGH (vets carry signal)"


def test_mechanism_system_tax() -> None:
    d = {
        "ALL": {"mean_delta": -0.5},
        "VET-AT-PEAK": {"n": 10, "mean_delta": -0.1},
        "YOUNG-PROSPECT": {"n": 10, "mean_delta": -0.9},
    }
    assert classify_mechanism(d) == "negative via SYSTEM-TAX (young players carry signal)"


def test_mechanism_both() -> None:
    d = {
        "ALL": {"mean_delta": -0.5},
        "VET-AT-PEAK": {"n": 10, "mean_delta": -0.5},
        "YOUNG-PROSPECT": {"n": 10, "mean_delta": -0.4},
    }
    assert classify_mechanism(d) == "negative via BOTH mechanisms"


def test_mechanism_small_buckets_inconclusive() -> None:
    d = {
        "ALL": {"mean_delta": 0.3},
        "VET-AT-PEAK": {"n": 2, "mean_delta": 1.0},
        "YOUNG-PROSPECT": {"n": 4, "mean_delta": 0.1},
    }
    assert classify_mechanism(d) == "positive (small buckets, inconclusive)"


def test_mechanism_vet_bucket_dominant() -> None:
    d = {
        "ALL": {"mean_delta": -0.5},
        "VET-AT-PEAK": {"n": 6, "mean_delta": -1.0},
        "YOUNG-PROSPECT": {"n": 2, "mean_delta": 0.0},
    }
    assert classify_mechanism(d) == "negative via SELL-HIGH (vet bucket dominant; young n=2)"
