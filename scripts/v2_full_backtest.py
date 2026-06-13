"""V2 full backtest — all four outcomes.

ARCHIVED — V3 is the production path (schema33/v3.2, scripts/benchmark_vs_naive.py).
Do not invest in fixing this script; V3 supersedes it with 28% MAE improvement
over the naïve baseline (D-51).

Known failure: PyMC sampling exits at initialization with
"Initial evaluation of model at starting point failed! y_obs: nan"
Root cause: when minimum_features_present < len(feature_cols), feature columns
that are entirely NaN in the training split produce NaN column-means; fillna()
then imputes NaN rather than a real value, which propagates through the feature
matrix into mu and y_obs. Fix would require dropping or zero-imputing all-NaN
columns before standardization — not worth doing since V3 replaced this model.

Runs xwoba / kpct / war / dollar_surplus through the train-2010-2020 /
test-2021-2024 split and prints per-outcome calibration, CRPS, and the
D-26 credible-feature list. Calibration coverage + credible-feature counts
are the actual diagnostics — single-trade case checks are not a smoke test.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from savage_trade_evaluator.modeling.v2.backtest import (
    backtest_outcome,
    print_backtest_report,
)


def main() -> None:
    """Run V2 backtest across all four outcomes."""
    outcomes = ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus")
    results = {}
    for o in outcomes:
        print()
        print("#" * 88)
        print(f"# {o.upper()}")
        print("#" * 88)
        try:
            result = backtest_outcome(
                outcome=o,
                train_end_season=2020,
                test_end_season=2024,
                minimum_features_present=5,
            )
        except ValueError as e:
            print(f"  SKIPPED: {e}")
            continue
        print_backtest_report(result)
        results[o] = result

    print()
    print("=" * 88)
    print("SUMMARY")
    print("=" * 88)
    for o, r in results.items():
        ncred = int(r.credible_features["credible"].sum())
        print(
            f"  {o:<16} train={r.train_n:>4} test={r.test_n:>4}  "
            f"MAE={r.test_mae:.4f}  CRPS={r.test_crps:.4f}  "
            f"cov90={r.coverage_90:.1%}  credible_features={ncred}"
        )


if __name__ == "__main__":
    main()
