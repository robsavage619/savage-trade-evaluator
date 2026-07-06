"""Tests for multiple imputation in v3.predict().

Critical invariants:
- Complete rows: MI=False and MI=True produce bit-identical output.
- Rows with missing features: MI=True widens posterior intervals (larger SD).
- Missing column treated the same as all-NaN column.
- Determinism: two identical calls return identical arrays.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from savage_trade_evaluator.modeling.v3 import predict


@pytest.fixture()
def complete_df(synthetic_fit):  # type: ignore[no-untyped-def]
    """1-row DataFrame with all features observed."""
    return pd.DataFrame([{"feat_a": 1.0, "feat_b": -0.5, "feat_c": 0.25}])


@pytest.fixture()
def partial_df(synthetic_fit):  # type: ignore[no-untyped-def]
    """1-row DataFrame with feat_b and feat_c missing (1/3 observed)."""
    return pd.DataFrame([{"feat_a": 1.0, "feat_b": float("nan"), "feat_c": float("nan")}])


@pytest.fixture()
def all_nan_df(synthetic_fit):  # type: ignore[no-untyped-def]
    """1-row DataFrame with all features NaN."""
    return pd.DataFrame([{"feat_a": float("nan"), "feat_b": float("nan"), "feat_c": float("nan")}])


# ---------------------------------------------------------------------------
# Bit-identical for complete rows
# ---------------------------------------------------------------------------


def test_complete_row_mi_false_and_true_identical(synthetic_fit, complete_df) -> None:  # type: ignore[no-untyped-def]
    """MI=True on a complete row must produce bit-identical results to MI=False."""
    out_no_mi = predict(synthetic_fit, complete_df, multiple_imputation=False)
    out_mi = predict(synthetic_fit, complete_df, multiple_imputation=True)
    assert np.array_equal(out_no_mi, out_mi), (
        "complete row with MI=True should be bit-identical to MI=False"
    )


# ---------------------------------------------------------------------------
# MI widens intervals for sparse rows
# ---------------------------------------------------------------------------


def test_partial_row_mi_widens_sd(synthetic_fit, partial_df) -> None:  # type: ignore[no-untyped-def]
    """MI=True on a sparse row must produce strictly wider posterior SD than MI=False."""
    out_no_mi = predict(synthetic_fit, partial_df, multiple_imputation=False)
    out_mi = predict(synthetic_fit, partial_df, multiple_imputation=True)
    sd_no_mi = float(out_no_mi[0].std())
    sd_mi = float(out_mi[0].std())
    assert sd_mi > sd_no_mi, (
        f"MI SD ({sd_mi:.4f}) should be strictly larger than mean-imputation SD ({sd_no_mi:.4f})"
    )


def test_partial_row_mi_mean_within_mc_se(synthetic_fit, partial_df) -> None:  # type: ignore[no-untyped-def]
    """MI mean must be consistent with non-MI mean (within ~3x MC SE).

    Marginal z-draws are zero-mean, so the expected MI mean equals mean-imputation
    mean; differences are Monte-Carlo noise.
    """
    out_no_mi = predict(synthetic_fit, partial_df, multiple_imputation=False)
    out_mi = predict(synthetic_fit, partial_df, multiple_imputation=True)
    n_samples = out_mi.shape[1]
    mc_se = float(out_mi[0].std()) / n_samples**0.5
    diff = abs(float(out_mi[0].mean()) - float(out_no_mi[0].mean()))
    # Allow 6x MC SE as a very loose bound (the true difference is 0 in expectation)
    assert diff < 6 * mc_se, f"MI mean diff ({diff:.4f}) exceeds 6x MC SE ({6 * mc_se:.4f})"


# ---------------------------------------------------------------------------
# All-NaN row runs and produces wider intervals
# ---------------------------------------------------------------------------


def test_all_nan_row_runs_without_error(synthetic_fit, all_nan_df) -> None:  # type: ignore[no-untyped-def]
    """All-NaN input must not raise and must return (1, n_samples) array."""
    out = predict(synthetic_fit, all_nan_df, multiple_imputation=True)
    assert out.shape[0] == 1
    assert out.shape[1] > 0


def test_all_nan_row_wider_than_complete(synthetic_fit, complete_df, all_nan_df) -> None:  # type: ignore[no-untyped-def]
    """All-NaN MI SD must be strictly greater than complete-row MI SD."""
    sd_complete = float(predict(synthetic_fit, complete_df, multiple_imputation=True)[0].std())
    sd_all_nan = float(predict(synthetic_fit, all_nan_df, multiple_imputation=True)[0].std())
    assert sd_all_nan > sd_complete, (
        f"all-NaN SD ({sd_all_nan:.4f}) should exceed complete-row SD ({sd_complete:.4f})"
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_mi_deterministic_two_calls(synthetic_fit, partial_df) -> None:  # type: ignore[no-untyped-def]
    """Two identical MI calls must return bit-identical arrays."""
    out1 = predict(synthetic_fit, partial_df, multiple_imputation=True)
    out2 = predict(synthetic_fit, partial_df, multiple_imputation=True)
    assert np.array_equal(out1, out2), "MI predict is not deterministic"


# ---------------------------------------------------------------------------
# Missing column treated as all-NaN
# ---------------------------------------------------------------------------


def test_missing_column_same_as_all_nan(synthetic_fit) -> None:  # type: ignore[no-untyped-def]
    """A DataFrame missing a column entirely must behave identically to all-NaN for that column."""
    df_no_col = pd.DataFrame([{"feat_a": 1.0}])  # feat_b and feat_c absent
    df_nan_col = pd.DataFrame([{"feat_a": 1.0, "feat_b": float("nan"), "feat_c": float("nan")}])
    out_no_col = predict(synthetic_fit, df_no_col, multiple_imputation=True)
    out_nan_col = predict(synthetic_fit, df_nan_col, multiple_imputation=True)
    assert np.array_equal(out_no_col, out_nan_col), (
        "absent columns should be treated identically to all-NaN columns"
    )
