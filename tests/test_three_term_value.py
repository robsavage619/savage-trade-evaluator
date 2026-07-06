"""Hermetic tests for three_term_value.py — salary aggregation (B1) and win curve (B2)."""

from __future__ import annotations

import duckdb

from savage_trade_evaluator.modeling.three_term_value import (
    _WIN_CURVE_MIDPOINT_2022_PLUS,
    _WIN_CURVE_MIDPOINT_PRE_2022,
    _playoff_prob,
    compute_cost_controlled_surplus,
    compute_playoff_revenue_delta,
)

# ---------------------------------------------------------------------------
# Minimal in-memory schema for Term-1 tests
# ---------------------------------------------------------------------------

_SETUP_SQL = """
CREATE TABLE trade_player_war_window (
    trade_event_id  INTEGER,
    mlb_player_id   INTEGER,
    to_team_bref    VARCHAR,
    trade_season    INTEGER,
    war_t_with_receiver DOUBLE,
    war_t_plus_1    DOUBLE,
    war_t_plus_2    DOUBLE,
    war_t_plus_3    DOUBLE
);
CREATE TABLE bwar_batting (
    mlb_id   INTEGER,
    year_id  INTEGER,
    salary   DOUBLE
);
CREATE TABLE bwar_pitching (
    mlb_id   INTEGER,
    year_id  INTEGER,
    salary   DOUBLE
);
"""


def _conn_with_schema() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute(_SETUP_SQL)
    return conn


# ---------------------------------------------------------------------------
# B1-1  Multi-year salary must be SUMMED, not averaged
# ---------------------------------------------------------------------------


def test_surplus_sums_salary_over_window() -> None:
    """4 seasons x $10M/yr = $40M salary; 4 WAR x $8M/WAR = $32M revenue -> surplus = -$8M."""
    conn = _conn_with_schema()

    # One player received in 2020, 4 WAR total (1 trade-year + 3 T+1..T+3)
    conn.execute(
        "INSERT INTO trade_player_war_window VALUES (1, 100, 'HOU', 2020, 1.0, 1.0, 1.0, 1.0)"
    )
    # Salary rows for seasons 2020, 2021, 2022, 2023 — $10M each
    for yr in range(2020, 2024):
        conn.execute("INSERT INTO bwar_batting VALUES (100, ?, 10_000_000.0)", [yr])

    surplus, notes = compute_cost_controlled_surplus(
        trade_event_id=1,
        receiver_bref="HOU",
        outcome_window_years=3,
        dollars_per_war=8_000_000.0,
        conn=conn,
    )
    # realized_war = 1+1+1+1 = 4; window_salary SUM = 4*10M = 40M
    # surplus = 4*8M - 40M = 32M - 40M = -8M
    assert abs(surplus - (-8_000_000.0)) < 1.0, f"expected -8M, got {surplus}"
    assert notes == ""


def test_surplus_not_avg_over_window() -> None:
    """Regression: prior AVG code would return 10M (one season avg) instead of SUM 40M."""
    conn = _conn_with_schema()

    conn.execute(
        "INSERT INTO trade_player_war_window VALUES (2, 200, 'NYY', 2019, 0.0, 2.0, 2.0, 2.0)"
    )
    for yr in range(2019, 2023):
        conn.execute("INSERT INTO bwar_pitching VALUES (200, ?, 10_000_000.0)", [yr])

    surplus, _ = compute_cost_controlled_surplus(2, "NYY", outcome_window_years=3, conn=conn)
    # 6 WAR x 8M = 48M; SUM salary 4 seasons x 10M = 40M -> surplus = 8M
    # If AVG were used: avg_salary = 10M (correct per-season avg, but only 1 row in
    # player_salary group) → SUM(avg_salary) = 10M → surplus would be 48M - 10M = 38M (wrong)
    assert abs(surplus - 8_000_000.0) < 1.0, f"expected 8M, got {surplus}"


# ---------------------------------------------------------------------------
# B1-2  Two-way player: salary in both bwar tables should be counted once/season
# ---------------------------------------------------------------------------


def test_two_way_player_salary_deduped() -> None:
    """Same player-season in both bwar tables must count only once (MAX dedup)."""
    conn = _conn_with_schema()

    # One player, one season, $12M in batting AND $12M in pitching → should count $12M once
    conn.execute(
        "INSERT INTO trade_player_war_window VALUES (3, 300, 'LAD', 2021, 0.0, 1.0, 1.0, 1.0)"
    )
    conn.execute("INSERT INTO bwar_batting  VALUES (300, 2021, 12_000_000.0)")
    conn.execute("INSERT INTO bwar_pitching VALUES (300, 2021, 12_000_000.0)")

    surplus, _ = compute_cost_controlled_surplus(3, "LAD", outcome_window_years=3, conn=conn)
    # 3 WAR x 8M = 24M; SUM(deduped salary 2021 only) = 12M -> surplus = 12M
    # Without dedup: SUM = 24M → surplus = 0M (wrong)
    assert abs(surplus - 12_000_000.0) < 1.0, f"expected 12M, got {surplus}"


# ---------------------------------------------------------------------------
# B1-3  Missing salary → $0 + notes
# ---------------------------------------------------------------------------


def test_missing_salary_treated_as_zero_with_note() -> None:
    conn = _conn_with_schema()

    conn.execute(
        "INSERT INTO trade_player_war_window VALUES (4, 400, 'BOS', 2018, 0.0, 2.0, 2.0, 2.0)"
    )
    # No salary rows inserted

    surplus, notes = compute_cost_controlled_surplus(4, "BOS", outcome_window_years=3, conn=conn)
    assert abs(surplus - (6 * 8_000_000.0)) < 1.0  # salary treated as 0
    assert "salary missing" in notes


# ---------------------------------------------------------------------------
# B1-4  Salary outside the window must be excluded
# ---------------------------------------------------------------------------


def test_salary_outside_window_excluded() -> None:
    """Season trade_season + N + 1 must not contribute to the salary sum."""
    conn = _conn_with_schema()

    conn.execute(
        "INSERT INTO trade_player_war_window VALUES (5, 500, 'ATL', 2020, 0.0, 1.0, 1.0, 1.0)"
    )
    # Only add salary for year 2024, which is outside trade_season + 3 = 2023
    conn.execute("INSERT INTO bwar_batting VALUES (500, 2024, 10_000_000.0)")

    surplus, notes = compute_cost_controlled_surplus(5, "ATL", outcome_window_years=3, conn=conn)
    # window_salary should be NULL (no row in range 2020-2023) → missing, treated as 0
    assert abs(surplus - (3 * 8_000_000.0)) < 1.0
    assert "salary missing" in notes


# ---------------------------------------------------------------------------
# B2-1  Era-aware midpoints: P(playoff) = 0.5 at the right win total
# ---------------------------------------------------------------------------


def test_playoff_prob_half_at_midpoint_pre_2022() -> None:
    p = _playoff_prob(_WIN_CURVE_MIDPOINT_PRE_2022, season=2021)
    assert abs(p - 0.5) < 1e-9, f"expected 0.5 at midpoint, got {p}"


def test_playoff_prob_half_at_midpoint_2022_plus() -> None:
    p = _playoff_prob(_WIN_CURVE_MIDPOINT_2022_PLUS, season=2023)
    assert abs(p - 0.5) < 1e-9, f"expected 0.5 at midpoint, got {p}"


def test_playoff_prob_uses_pre_2022_curve_for_2021() -> None:
    # At 86 wins in 2021 (10-team era) P should be < 0.5 (bar is 89)
    p = _playoff_prob(86.0, season=2021)
    assert p < 0.5


def test_playoff_prob_uses_2022_curve_for_2022() -> None:
    # At 86 wins in 2022 (12-team era) P should be exactly 0.5
    p = _playoff_prob(86.0, season=2022)
    assert abs(p - 0.5) < 1e-9


def test_playoff_prob_monotone_within_era() -> None:
    """More wins = higher playoff probability."""
    for season in [2019, 2023]:
        probs = [_playoff_prob(w, season) for w in [70, 80, 86, 90, 100]]
        assert probs == sorted(probs), f"not monotone for season={season}"


# ---------------------------------------------------------------------------
# B2-2  compute_playoff_revenue_delta notes include era label
# ---------------------------------------------------------------------------


def test_revenue_delta_notes_include_era_label() -> None:
    _, notes = compute_playoff_revenue_delta(82.0, 2.0, trade_season=2023)
    assert "12-team" in notes

    _, notes_old = compute_playoff_revenue_delta(88.0, 2.0, trade_season=2019)
    assert "10-team" in notes_old
