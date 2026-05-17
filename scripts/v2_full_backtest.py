"""V2 full backtest — all four outcomes.

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
