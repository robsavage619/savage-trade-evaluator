"""Hermetic tests for the FV-to-WAR prospect calibration lookup."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from savage_trade_evaluator.storage import db
from savage_trade_evaluator.storage.schemas import DDL_STATEMENTS
from savage_trade_evaluator.valuation import prospect
from savage_trade_evaluator.valuation.prospect import ProspectScore, score_prospect

_CALIBRATION_DDL = next(s for s in DDL_STATEMENTS if "prospect_fv_calibration" in s)


def _ps(fv: int, fitted: float, n: int = 10) -> ProspectScore:
    return ProspectScore(
        fv=fv,
        fitted_war_5yr=fitted,
        war_p10=fitted - 2.0,
        war_p90=fitted + 2.0,
        n_comparables=n,
        mean_war_5yr=fitted + 0.1,
        median_war_5yr=fitted - 0.1,
    )


@pytest.fixture()
def two_grade_table(monkeypatch: pytest.MonkeyPatch) -> dict[int, ProspectScore]:
    table = {50: _ps(50, 2.0, n=20), 60: _ps(60, 6.0, n=8)}
    monkeypatch.setattr(prospect, "_load_calibration", lambda: table)
    return table


@pytest.mark.parametrize("fv", [39, 86, 100])
def test_rejects_fv_out_of_range(fv: int) -> None:
    with pytest.raises(ValueError, match="outside the valid range"):
        score_prospect(fv)


def test_empty_table_returns_zero_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prospect, "_load_calibration", dict)
    score = score_prospect(55)
    assert score.fv == 55
    assert score.fitted_war_5yr == 0.0
    assert score.n_comparables == 0


def test_exact_grade_returns_table_entry(two_grade_table: dict[int, ProspectScore]) -> None:
    assert score_prospect(60) is two_grade_table[60]


def test_interpolates_midpoint_between_grades(two_grade_table: dict[int, ProspectScore]) -> None:
    score = score_prospect(55)
    assert score.fv == 55
    assert score.fitted_war_5yr == pytest.approx(4.0)
    assert score.war_p10 == pytest.approx(2.0)
    assert score.war_p90 == pytest.approx(6.0)
    assert score.n_comparables == 8  # min of the two adjacent grades


def test_clamps_below_lowest_grade(two_grade_table: dict[int, ProspectScore]) -> None:
    assert score_prospect(45) is two_grade_table[50]


def test_clamps_above_highest_grade(two_grade_table: dict[int, ProspectScore]) -> None:
    assert score_prospect(80) is two_grade_table[60]


def test_loads_calibration_from_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "calibration.db"
    conn = duckdb.connect(str(db_file))
    conn.execute(_CALIBRATION_DDL)
    conn.execute(
        "INSERT INTO prospect_fv_calibration "
        "(fv, n_comparables, mean_war_5yr, median_war_5yr, std_war_5yr, "
        "fitted_war_5yr, fitted_war_p10, fitted_war_p90, cohort_start, cohort_end) "
        "VALUES (50, 12, 3.1, 2.4, 1.0, 3.0, 0.5, 6.2, 2017, 2020)"
    )
    conn.close()

    monkeypatch.setattr(db, "DUCKDB_PATH", db_file)
    prospect.invalidate_cache()
    try:
        score = score_prospect(50)
        assert score.fitted_war_5yr == 3.0
        assert score.war_p10 == 0.5
        assert score.war_p90 == 6.2
        assert score.n_comparables == 12
        assert score.mean_war_5yr == 3.1
        assert score.median_war_5yr == 2.4
    finally:
        prospect.invalidate_cache()
