"""Unit tests for the trade-cycle solver — no DB access required."""

from __future__ import annotations

import pandas as pd
import pytest

from savage_trade_evaluator.analysis.trade_cycles import Cycle, find_cycles


def _matrix(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows)


# Four-club synthetic matrix:
#   - Diagonal (keep values): A keeps P1 @ 3.0, B keeps P2 @ 3.0,
#                              C keeps P3 @ 2.0, D keeps P4 @ 2.0
#   - Known valid 2-cycle: A↔B (A sends P1 to B → uplift 1.0; B sends P2 to A → uplift 0.5)
#   - Known valid 3-cycle: B→C→D→B (each leg uplift 0.4, distinct from the A↔B 2-cycle)
#   No decoy rows here — decoy blocking is tested in its own mini-matrix below.
FIXTURE_ROWS = [
    # --- diagonals (keep values) ---
    dict(
        mlb_id=1,
        player_name="P1",
        sender_bref="A",
        receiver_bref="A",
        prior_war=3.0,
        war_delta_mean=0.0,
    ),
    dict(
        mlb_id=2,
        player_name="P2",
        sender_bref="B",
        receiver_bref="B",
        prior_war=3.0,
        war_delta_mean=0.0,
    ),
    dict(
        mlb_id=3,
        player_name="P3",
        sender_bref="C",
        receiver_bref="C",
        prior_war=2.0,
        war_delta_mean=0.0,
    ),
    dict(
        mlb_id=4,
        player_name="P4",
        sender_bref="D",
        receiver_bref="D",
        prior_war=2.0,
        war_delta_mean=0.0,
    ),
    # --- 2-cycle A↔B ---
    # B acquires P1 from A: value(P1,B) = 3.0 + 1.0 = 4.0; keep(P1) = 3.0; uplift_B = 1.0
    dict(
        mlb_id=1,
        player_name="P1",
        sender_bref="A",
        receiver_bref="B",
        prior_war=3.0,
        war_delta_mean=1.0,
    ),
    # A acquires P2 from B: value(P2,A) = 3.0 + 0.5 = 3.5; keep(P2) = 3.0; uplift_A = 0.5
    dict(
        mlb_id=2,
        player_name="P2",
        sender_bref="B",
        receiver_bref="A",
        prior_war=3.0,
        war_delta_mean=0.5,
    ),
    # --- 3-cycle B→C→D→B ---
    # C acquires P2 from B: value(P2,C) = 3.0+0.4=3.4; keep(P2)=3.0; uplift_C = 0.4
    dict(
        mlb_id=2,
        player_name="P2",
        sender_bref="B",
        receiver_bref="C",
        prior_war=3.0,
        war_delta_mean=0.4,
    ),
    # D acquires P3 from C: value(P3,D) = 2.0+0.4=2.4; keep(P3)=2.0; uplift_D = 0.4
    dict(
        mlb_id=3,
        player_name="P3",
        sender_bref="C",
        receiver_bref="D",
        prior_war=2.0,
        war_delta_mean=0.4,
    ),
    # B acquires P4 from D: value(P4,B) = 2.0+0.4=2.4; keep(P4)=2.0; uplift_B = 0.4
    dict(
        mlb_id=4,
        player_name="P4",
        sender_bref="D",
        receiver_bref="B",
        prior_war=2.0,
        war_delta_mean=0.4,
    ),
]


@pytest.fixture()
def matrix() -> pd.DataFrame:
    return _matrix(*FIXTURE_ROWS)


def test_find_cycles_detects_two_cycle(matrix: pd.DataFrame) -> None:
    cycles = find_cycles(matrix, max_len=2, min_gain=0.25)
    two_cycles = [c for c in cycles if len(c.clubs) == 2]
    assert len(two_cycles) == 1
    ab = two_cycles[0]
    assert set(ab.clubs) == {"A", "B"}
    assert abs(ab.total_gain - 1.5) < 1e-9


def test_find_cycles_detects_three_cycle(matrix: pd.DataFrame) -> None:
    cycles = find_cycles(matrix, max_len=3, min_gain=0.25)
    three_cycles = [c for c in cycles if len(c.clubs) == 3]
    assert len(three_cycles) == 1
    bcd = three_cycles[0]
    assert set(bcd.clubs) == {"B", "C", "D"}
    assert abs(bcd.total_gain - 1.2) < 1e-9


def test_find_cycles_blocks_decoy_two_cycle() -> None:
    # Isolated matrix: A→D has uplift 0.3 but D→A has uplift 0.05 < min_gain.
    # The A↔D 2-cycle must not appear.
    mini_rows = [
        dict(mlb_id=1, player_name="P1", sender_bref="A", receiver_bref="A",
             prior_war=3.0, war_delta_mean=0.0),
        dict(mlb_id=4, player_name="P4", sender_bref="D", receiver_bref="D",
             prior_war=2.0, war_delta_mean=0.0),
        dict(mlb_id=1, player_name="P1", sender_bref="A", receiver_bref="D",
             prior_war=3.0, war_delta_mean=0.3),
        dict(mlb_id=4, player_name="P4", sender_bref="D", receiver_bref="A",
             prior_war=2.0, war_delta_mean=0.05),
    ]
    mini = pd.DataFrame(mini_rows)
    cycles = find_cycles(mini, max_len=2, min_gain=0.25)
    assert cycles == []


def test_find_cycles_dedup_no_double_count(matrix: pd.DataFrame) -> None:
    cycles = find_cycles(matrix, max_len=3, min_gain=0.25)
    club_sets = [frozenset(c.clubs) for c in cycles]
    assert len(club_sets) == len(set(club_sets)), "duplicate club-sets in output"


def test_find_cycles_sorted_by_total_gain(matrix: pd.DataFrame) -> None:
    cycles = find_cycles(matrix, max_len=3, min_gain=0.25)
    gains = [c.total_gain for c in cycles]
    assert gains == sorted(gains, reverse=True)


def test_find_cycles_empty_matrix_returns_empty() -> None:
    empty = _matrix()
    assert find_cycles(empty) == []


def test_cycle_dataclass_is_hashable() -> None:
    c = Cycle(
        clubs=("A", "B"),
        players=((1, "P1"), (2, "P2")),
        gains={"A": 0.5, "B": 1.0},
        total_gain=1.5,
    )
    assert hash(c) is not None
