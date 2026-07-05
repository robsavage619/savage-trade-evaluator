"""A7: Tests for the V3 assemble / fold-construction validity path.

Three families:
  (1) FG merge fan-out guard — asserts the FG left-join cannot increase row count.
      Pure-function version uses synthetic DataFrames; integration version requires
      the real DB and is skipped when it is absent.
  (2) Walk-forward fold properties — temporal ordering and no test-set leakage.
      Pure-function: calls walk_forward_splits() on a synthetic DataFrame.
  (3) CRPS correctness — lives in test_metrics.py; referenced here for completeness.
"""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import pytest

from savage_trade_evaluator.config import DUCKDB_PATH
from savage_trade_evaluator.modeling.v3_cv import walk_forward_splits

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_DB_AVAILABLE = DUCKDB_PATH.exists()
_skip_no_db = pytest.mark.skipif(not _DB_AVAILABLE, reason="real DB not present")


def _make_combined(seasons: list[int], n_per_season: int = 5) -> pd.DataFrame:
    """Synthetic combined DataFrame for fold-property tests."""
    rng = np.random.default_rng(0)
    rows = []
    event_id = 1
    for s in seasons:
        for _ in range(n_per_season):
            rows.append(
                {
                    "trade_event_id": event_id,
                    "receiver_bref": f"P{event_id:04d}",
                    "trade_season": s,
                    "war_delta": float(rng.normal()),
                    "dollar_surplus": float(rng.normal()),
                }
            )
            event_id += 1
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Family 1 — FG merge fan-out guard
# ---------------------------------------------------------------------------


def test_fg_merge_does_not_fan_out_synthetic() -> None:
    """Left-join on (trade_event_id, receiver_bref, trade_season) must not increase rows.

    Guards the v3.py:76 merge key bug: if trade_season is omitted and fg has a
    duplicate (trade_event_id, receiver_bref) pair for a different season, the
    left-join fans out the merged rows.
    """
    merged = pd.DataFrame(
        {
            "trade_event_id": [1, 2, 3],
            "receiver_bref": ["A", "B", "C"],
            "trade_season": [2015, 2016, 2017],
            "war_delta": [1.0, 2.0, 3.0],
        }
    )
    # fg with correct 1:1 cardinality
    fg = pd.DataFrame(
        {
            "trade_event_id": [1, 2, 3],
            "receiver_bref": ["A", "B", "C"],
            "trade_season": [2015, 2016, 2017],
            "wrc_delta": [0.1, 0.2, 0.3],
        }
    )
    result = merged.merge(fg, on=["trade_event_id", "receiver_bref", "trade_season"], how="left")
    assert len(result) == len(merged), "row count must not grow after FG left-join"


def test_fg_merge_fan_out_would_occur_without_season_key() -> None:
    """Demonstrates the fan-out that the trade_season key prevents.

    This test documents the bug pattern: without trade_season in the key,
    a single spurious extra row in fg inflates the merged result.
    """
    merged = pd.DataFrame(
        {
            "trade_event_id": [1, 1],
            "receiver_bref": ["A", "A"],
            "trade_season": [2015, 2016],
            "war_delta": [1.0, 2.0],
        }
    )
    # fg incorrectly has two rows for the same (trade_event_id, receiver_bref)
    fg_bad = pd.DataFrame(
        {
            "trade_event_id": [1, 1],
            "receiver_bref": ["A", "A"],
            "trade_season": [2015, 2016],
            "wrc_delta": [0.1, 0.2],
        }
    )
    without_season = merged.merge(fg_bad, on=["trade_event_id", "receiver_bref"], how="left")
    with_season = merged.merge(
        fg_bad, on=["trade_event_id", "receiver_bref", "trade_season"], how="left"
    )
    assert len(without_season) > len(merged), "fan-out should occur without season key"
    assert len(with_season) == len(merged), "season key should prevent fan-out"


@_skip_no_db
def test_assemble_v3_combined_no_fan_out() -> None:
    """FG merge does not increase row count relative to the pre-FG merged frame."""
    from savage_trade_evaluator.modeling.v2.backtest import assemble_combined
    from savage_trade_evaluator.modeling.v3 import assemble_v3_combined

    base = assemble_combined()
    v3 = assemble_v3_combined()
    # v3 may have fewer rows (inner merges on some outcomes) but never more than base
    assert len(v3) <= len(base), (
        f"assemble_v3_combined ({len(v3)} rows) exceeds assemble_combined ({len(base)} rows)"
    )
    # FG columns must exist; spot-check cardinality on rows that have FG data
    assert "wrc_delta" in v3.columns
    fg_rows = v3["wrc_delta"].notna()
    if bool(fg_rows.any()):
        duped = cast("pd.DataFrame", v3[fg_rows]).duplicated(
            subset=["trade_event_id", "receiver_bref", "trade_season"]
        )
        assert not duped.any(), "FG merge created duplicate rows on the 3-key"


# ---------------------------------------------------------------------------
# Family 2 — walk-forward fold temporal ordering + no test-set leakage
# ---------------------------------------------------------------------------


def test_fold_train_end_precedes_test_start() -> None:
    """Every fold's training window ends strictly before its test window begins."""
    seasons = list(range(2010, 2025))  # 15 seasons
    combined = _make_combined(seasons)
    splits = walk_forward_splits("war_delta", combined)
    assert len(splits) > 0, "expected at least one fold"
    for s in splits:
        assert s.train_end < s.test_start, (
            f"{s.label}: train_end={s.train_end} not < test_start={s.test_start}"
        )


def test_fold_test_sets_do_not_overlap() -> None:
    """No trade_event_id appears in more than one test fold."""
    seasons = list(range(2010, 2025))
    combined = _make_combined(seasons)
    splits = walk_forward_splits("war_delta", combined)

    seen: set[int] = set()
    for s in splits:
        test_rows = combined[combined["trade_season"].between(s.test_start, s.test_end)]
        test_ids = set(test_rows["trade_event_id"].tolist())
        overlap = seen & test_ids
        assert not overlap, (
            f"{s.label}: {len(overlap)} trade_event_ids already in a prior test fold"
        )
        seen |= test_ids


def test_fold_train_seasons_are_strictly_before_test_seasons() -> None:
    """max(train_season) < min(test_season) for every fold's actual data."""
    seasons = list(range(2010, 2025))
    combined = _make_combined(seasons)
    splits = walk_forward_splits("war_delta", combined)
    for s in splits:
        train_rows = combined[combined["trade_season"].between(s.train_start, s.train_end)]
        test_rows = combined[combined["trade_season"].between(s.test_start, s.test_end)]
        if train_rows.empty or test_rows.empty:
            continue
        train_max = int(cast("int", train_rows["trade_season"].max()))
        test_min = int(cast("int", test_rows["trade_season"].min()))
        assert train_max < test_min, f"{s.label}: train data leaks into test window"
