"""Q-01 / Q-02 / Q-07 empirical experiments.

Q-01  Trade scope cutoff — meaningful trades vs. all trades.
      Filter: acquired player quality >= 1.0 (≈ above-replacement quality tier).
      Compare credible-feature counts and MAE across the two populations.

Q-02  Outcome window length — 3yr vs. 5yr.
      Compare war_delta and dollar_surplus MAE/CRPS/coverage.
      Expects bWAR data through 2024; trades ≤2019 have full 5yr windows.

Q-07  Post-trade transition cost — window starting T+1 vs. T+2.
      Hypothesis: skipping the transition year reduces noise and tightens
      credible-feature counts.  Window T+2..T+4 (same 3 years, later start).

Outputs a compact comparison table to stdout.  No file artifacts.
"""

from __future__ import annotations

import logging
import warnings

import pandas as pd

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

from savage_trade_evaluator.modeling.v2.backtest import assemble_combined
from savage_trade_evaluator.modeling.v2.outcomes import build_outcomes_windowed
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    backtest_outcome_v3,
    print_backtest_report,
)

WAR_OUTCOMES = ("war_delta", "dollar_surplus")
ALL_OUTCOMES = ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus")


def _metrics(r) -> dict:
    return {
        "train_n": r.train_n,
        "test_n": r.test_n,
        "mae": round(r.test_mae, 4),
        "crps": round(r.test_crps, 4),
        "cov90": round(r.coverage_90, 3),
        "credible": int(r.credible_features["credible"].sum()),
    }


def run_q01() -> None:
    print("\n" + "=" * 88)
    print("Q-01  TRADE SCOPE CUTOFF: all trades vs. meaningful trades only")
    print("=" * 88)
    print("(meaningful = receiver_acquired_player_quality >= 1.0 ≈ above-replacement tier)")

    rows = []
    combined = assemble_combined()
    for outcome in ALL_OUTCOMES:
        r_all = backtest_outcome_v3(outcome, combined=combined)
        r_filt = backtest_outcome_v3(outcome, combined=combined, meaningful_trades_only=True)
        rows.append({
            "outcome": outcome,
            "scope": "all",
            **_metrics(r_all),
        })
        rows.append({
            "outcome": outcome,
            "scope": "meaningful",
            **_metrics(r_filt),
        })

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


def run_q02() -> None:
    print("\n" + "=" * 88)
    print("Q-02  OUTCOME WINDOW LENGTH: 3yr (T+1..T+3) vs. 5yr (T+1..T+5)")
    print("=" * 88)
    print("Note: 5yr restricts to trades ≤2019 for full windows. Expect lower train_n.")

    base_combined = assemble_combined()
    outcomes_5yr = build_outcomes_windowed(war_window_start=1, war_window_end=5)
    combined_5yr = assemble_combined(outcomes_df=outcomes_5yr)

    rows = []
    for outcome in WAR_OUTCOMES:
        r3 = backtest_outcome_v3(outcome, combined=base_combined)
        r5 = backtest_outcome_v3(outcome, combined=combined_5yr)
        rows.append({"outcome": outcome, "window": "3yr", **_metrics(r3)})
        rows.append({"outcome": outcome, "window": "5yr", **_metrics(r5)})

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


def run_q07() -> None:
    print("\n" + "=" * 88)
    print("Q-07  TRANSITION COST: window T+1..T+3 vs. T+2..T+4 (skip transition year)")
    print("=" * 88)

    base_combined = assemble_combined()
    outcomes_shifted = build_outcomes_windowed(war_window_start=2, war_window_end=4)
    combined_shifted = assemble_combined(outcomes_df=outcomes_shifted)

    rows = []
    for outcome in WAR_OUTCOMES:
        r_std = backtest_outcome_v3(outcome, combined=base_combined)
        r_shift = backtest_outcome_v3(outcome, combined=combined_shifted)
        rows.append({"outcome": outcome, "window_start": "T+1", **_metrics(r_std)})
        rows.append({"outcome": outcome, "window_start": "T+2", **_metrics(r_shift)})

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


if __name__ == "__main__":
    run_q01()
    run_q02()
    run_q07()
    print("\nDone.")
