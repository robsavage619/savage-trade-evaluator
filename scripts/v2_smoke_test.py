"""V2 smoke test — wire-check the new module end-to-end on one outcome.

Builds features + outcomes + fits multilevel + scores backtest for the
xwOBA outcome (V1's R-19 highlight finding). If V2 reproduces credibility
on the same data, the wiring is right.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from savage_trade_evaluator.modeling.v2.backtest import (
    backtest_outcome,
    print_backtest_report,
)
from savage_trade_evaluator.modeling.v2.features import build_feature_matrix
from savage_trade_evaluator.modeling.v2.outcomes import build_outcomes


def main() -> None:
    """Run the V2 smoke test on xwoba_delta."""
    print("=== V2 SMOKE TEST: data layer ===")
    features = build_feature_matrix()
    print(f"  feature_matrix: {len(features)} rows, {features.shape[1]} cols")
    print(f"  trade_seasons:  {features['trade_season'].min()}-{features['trade_season'].max()}")
    print(f"  regimes:        {features['regime_id'].nunique()}")
    print()

    outcomes = build_outcomes()
    print(f"  outcomes:       {len(outcomes)} rows")
    for col in ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus"):
        nn = outcomes[col].notna().sum()
        print(f"    {col}: {nn} non-null")
    print()

    print("=== V2 SMOKE TEST: xwOBA backtest ===")
    result = backtest_outcome(
        outcome="xwoba_delta",
        train_end_season=2020,
        test_end_season=2024,
        minimum_features_present=5,  # accept partial coverage; impute the rest
    )
    print_backtest_report(result)


if __name__ == "__main__":
    main()
