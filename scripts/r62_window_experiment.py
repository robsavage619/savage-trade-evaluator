"""R-62: Outcome window experiment — T+1..T+4 vs current T+2..T+5.

Tests whether including the transition year (T+1) while dropping T+5
improves or hurts predictive accuracy on war_delta and surplus_wins.

Q-07 established that skipping T+1 gave +30% MAE improvement on the
shorter window; Q-02 showed T+5 adds credible features. This experiment
tests whether those findings hold in the full T+2..T+5 context vs T+1..T+4.

Expected outcome: T+2..T+5 should win (confirms Q-07 + Q-02 combined).
Any surprising result should be documented in ADR log (trade-eval--decisions.md).
"""

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.modeling.v2.outcomes import build_outcomes_windowed
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    _split_and_impute,
    assemble_v3_combined,
    backtest_outcome_v3,
)
from savage_trade_evaluator.modeling.v2.backtest import assemble_combined


def _assemble_with_window(war_start: int, war_end: int) -> pd.DataFrame:
    windowed = build_outcomes_windowed(
        war_window_start=war_start,
        war_window_end=war_end,
    )[["trade_event_id", "receiver_bref", "trade_season", "war_delta", "surplus_wins"]]
    from savage_trade_evaluator.modeling.v2.outcomes import build_outcomes
    std = build_outcomes()
    merged = std.drop(columns=["war_delta", "surplus_wins"]).merge(
        windowed, on=["trade_event_id", "receiver_bref", "trade_season"], how="left"
    )
    return assemble_combined(outcomes_df=merged)


def _run(label: str, combined: pd.DataFrame, outcome: str) -> dict:
    feature_cols = V3_OUTCOME_FEATURES[outcome]
    train, test = _split_and_impute(
        outcome=outcome,
        feature_cols=feature_cols,
        combined=combined,
    )
    result = backtest_outcome_v3(
        outcome=outcome,
        train=train,
        test=test,
        feature_cols=feature_cols,
    )
    credible = int(result.credible_features["credible"].sum())
    return {
        "label": label,
        "outcome": outcome,
        "train_n": result.train_n,
        "test_n": result.test_n,
        "crps": round(result.test_crps, 4),
        "mae": round(result.test_mae, 4),
        "cov90": round(result.coverage_90, 3),
        "credible_features": credible,
    }


def main() -> None:
    windows = {
        "T+2..T+5 (current)": (2, 5),
        "T+1..T+4 (alt)": (1, 4),
    }
    outcomes = ("war_delta", "surplus_wins")
    rows = []

    for label, (ws, we) in windows.items():
        print(f"\nAssembling window {label}…")
        combined = _assemble_with_window(ws, we)
        for outcome in outcomes:
            print(f"  Fitting {outcome}…")
            rows.append(_run(label, combined, outcome))

    df = pd.DataFrame(rows)
    print("\n" + "=" * 90)
    print("OUTCOME WINDOW COMPARISON  (R-62)")
    print("=" * 90)
    print(df.to_string(index=False))
    print()
    print("Lower CRPS/MAE = better. cov90 target = 0.90.")
    print("If T+2..T+5 wins on both, confirms Q-07 + Q-02 combined findings.")


if __name__ == "__main__":
    main()
