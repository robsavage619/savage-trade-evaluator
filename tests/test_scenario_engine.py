"""Hermetic tests for scenario_engine coverage and attribution functions."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from savage_trade_evaluator.modeling.production_fit import MODEL_VERSION
from savage_trade_evaluator.modeling.scenario_engine import (
    attribute_score,
    coverage_report,
    score_hypothetical,
)
from savage_trade_evaluator.modeling.v3 import V3FitResult

# ---------------------------------------------------------------------------
# coverage_report
# ---------------------------------------------------------------------------


def test_coverage_all_observed(synthetic_fit: V3FitResult) -> None:
    df = pd.DataFrame([{"feat_a": 1.0, "feat_b": 2.0, "feat_c": 3.0}])
    cov = coverage_report(df, synthetic_fit)
    assert cov["n_observed"] == 3
    assert cov["n_imputed"] == 0
    assert cov["grade"] == "A"
    assert cov["imputed_features"] == []


def test_coverage_one_third_observed(synthetic_fit: V3FitResult) -> None:
    """1/3 observed = 0.333 fraction => grade D."""
    df = pd.DataFrame([{"feat_a": 1.0, "feat_b": float("nan"), "feat_c": float("nan")}])
    cov = coverage_report(df, synthetic_fit)
    assert cov["n_observed"] == 1
    assert cov["n_imputed"] == 2
    assert cov["grade"] == "D"
    assert sorted(cov["imputed_features"]) == ["feat_b", "feat_c"]


def test_coverage_absent_column_counts_as_imputed(synthetic_fit: V3FitResult) -> None:
    """A column that's not in the DataFrame at all should count as imputed."""
    df = pd.DataFrame([{"feat_a": 1.0}])  # feat_b and feat_c absent
    cov = coverage_report(df, synthetic_fit)
    assert cov["n_imputed"] == 2
    assert "feat_b" in cov["imputed_features"]
    assert "feat_c" in cov["imputed_features"]


def test_coverage_grade_boundaries(synthetic_fit: V3FitResult) -> None:
    """Grade thresholds: A>=0.8, B>=0.6, C>=0.4, D<0.4."""
    # All 3 observed -> 1.0 -> A
    df_a = pd.DataFrame([{"feat_a": 1.0, "feat_b": 2.0, "feat_c": 3.0}])
    assert coverage_report(df_a, synthetic_fit)["grade"] == "A"

    # 2/3 observed -> 0.667 -> B
    df_b = pd.DataFrame([{"feat_a": 1.0, "feat_b": 2.0, "feat_c": float("nan")}])
    assert coverage_report(df_b, synthetic_fit)["grade"] == "B"

    # 1/3 observed -> 0.333 -> D (skips C for 3-feature fit)
    df_d = pd.DataFrame([{"feat_a": 1.0, "feat_b": float("nan"), "feat_c": float("nan")}])
    assert coverage_report(df_d, synthetic_fit)["grade"] == "D"


# ---------------------------------------------------------------------------
# attribute_score
# ---------------------------------------------------------------------------


def test_attribute_score_exact_math(synthetic_fit: V3FitResult) -> None:
    """With known constant betas, reconstructed_mean should equal analytic value."""
    # alpha0 = 0.1, y_std = 2.0, y_mean = 1.0
    # baseline = 0.1 * 2.0 + 1.0 = 1.2
    # beta = [0.4, -0.2, 0.0], x_z = [1.0, 1.0, 1.0] (all features at 1 SD)
    # contribution_a = 0.4 * 1.0 * 2.0 = 0.8
    # contribution_b = -0.2 * 1.0 * 2.0 = -0.4
    # sum_all = 0.4
    # reconstructed = 1.2 + 0.4 = 1.6
    df = pd.DataFrame([{"feat_a": 1.0, "feat_b": 1.0, "feat_c": 1.0}])
    attr = attribute_score(synthetic_fit, df, top_k=5)
    assert abs(attr["baseline"] - 1.2) < 1e-6
    assert abs(attr["reconstructed_mean"] - 1.6) < 1e-6
    assert abs(attr["sum_all"] - 0.4) < 1e-6


def test_attribute_score_nan_contributes_zero(synthetic_fit: V3FitResult) -> None:
    """NaN features are zeroed in z-space; their contribution must be 0."""
    df = pd.DataFrame([{"feat_a": float("nan"), "feat_b": float("nan"), "feat_c": float("nan")}])
    attr = attribute_score(synthetic_fit, df, top_k=5)
    for contrib in attr["top_contributors"]:
        assert contrib["contribution"] == 0.0
    # reconstructed_mean should equal baseline (no feature signal)
    assert abs(attr["reconstructed_mean"] - attr["baseline"]) < 1e-6


def test_attribute_score_observed_flag(synthetic_fit: V3FitResult) -> None:
    """NaN features should be marked as not observed; present features as observed."""
    df = pd.DataFrame([{"feat_a": 1.5, "feat_b": float("nan"), "feat_c": 0.0}])
    attr = attribute_score(synthetic_fit, df, top_k=5)
    by_feat = {c["feature"]: c for c in attr["top_contributors"]}
    assert by_feat["feat_a"]["observed"] is True
    assert by_feat["feat_b"]["observed"] is False
    assert by_feat["feat_c"]["observed"] is True


def test_attribute_score_top_k_ordering(synthetic_fit: V3FitResult) -> None:
    """top_contributors must be sorted by |contribution| descending."""
    df = pd.DataFrame([{"feat_a": 2.0, "feat_b": 0.5, "feat_c": 0.1}])
    attr = attribute_score(synthetic_fit, df, top_k=5)
    contribs = [abs(c["contribution"]) for c in attr["top_contributors"]]
    assert contribs == sorted(contribs, reverse=True)


# ---------------------------------------------------------------------------
# score_hypothetical payload shape + model_version constant
# ---------------------------------------------------------------------------


def test_score_hypothetical_payload_has_coverage_and_model_version(
    synthetic_fit: V3FitResult,
) -> None:
    """score_hypothetical() payload must include coverage per outcome and MODEL_VERSION."""
    df = pd.DataFrame([{"feat_a": 1.0, "feat_b": 1.0, "feat_c": 1.0}])

    with patch(
        "savage_trade_evaluator.modeling.scenario_engine.get_fit",
        return_value=synthetic_fit,
    ):
        result = score_hypothetical(df, outcomes=("war_delta",), receiver_bref="HOU")

    assert result["model_version"] == MODEL_VERSION
    wd = result["war_delta"]
    assert "coverage" in wd
    assert "attribution" in wd
    assert "data_coverage" in result
    assert result["data_coverage"]["grade"] in ("A", "B", "C", "D")
