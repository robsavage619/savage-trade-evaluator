"""R-45: contention-window score ablation.

Three ablations testing whether ``receiver_contention_window_score`` carries
independent signal beyond what the rest of the feature set provides:

1. Baseline — war_delta with ALL_FEATURES (current V3 default).
   Establishes the feature's credibility in the full collinear context.

2. Isolated — war_delta with ACQUIRED_PLAYER_FEATURES + contention score only.
   No other team features. Tests whether the signal survives without
   team-feature collinearity masking or amplifying it.

3. Small-n outcomes — xwoba_delta and kpct_delta with ACQUIRED_PLAYER_FEATURES
   + contention score. R-35 found player-only features best for these outcomes;
   this tests whether adding contention context changes that conclusion.

Per D-26: credible = 90% CI excludes zero AND directional mass >= 95%.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from savage_trade_evaluator.modeling.v2.features import (
    ACQUIRED_PLAYER_FEATURES,
    ALL_FEATURES,
)
from savage_trade_evaluator.modeling.v3 import (
    V3BacktestResult,
    backtest_outcome_v3,
    print_backtest_report,
)

_CONTENTION_SCORE = "receiver_contention_window_score"

_ABLATIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Baseline",
        "war_delta",
        ALL_FEATURES,
    ),
    (
        "Isolated",
        "war_delta",
        ACQUIRED_PLAYER_FEATURES + (_CONTENTION_SCORE,),
    ),
    (
        "Small-n xwoba",
        "xwoba_delta",
        ACQUIRED_PLAYER_FEATURES + (_CONTENTION_SCORE,),
    ),
    (
        "Small-n kpct",
        "kpct_delta",
        ACQUIRED_PLAYER_FEATURES + (_CONTENTION_SCORE,),
    ),
)


def _contention_credibility(result: V3BacktestResult) -> tuple[bool, float, float, float]:
    """Return (credible, mean_beta, p05, p95) for the contention score feature.

    Returns (False, nan, nan, nan) if the feature was not in the fit.
    """
    import math

    cf = result.credible_features
    row = cf[cf["feature"] == _CONTENTION_SCORE]
    if row.empty:
        return False, math.nan, math.nan, math.nan
    r = row.iloc[0]
    return bool(r["credible"]), float(r["mean_beta"]), float(r["p05"]), float(r["p95"])


def main() -> None:
    """Run all three R-45 ablations and print a structured summary."""
    results: list[tuple[str, str, V3BacktestResult]] = []

    for label, outcome, feature_cols in _ABLATIONS:
        print()
        print("#" * 88)
        print(f"# R-45 ablation: {label}  outcome={outcome}  features={len(feature_cols)}")
        print("#" * 88)
        try:
            result = backtest_outcome_v3(
                outcome=outcome,
                feature_cols=feature_cols,
                draws=1500,
                tune=2000,
            )
        except ValueError as exc:
            print(f"  SKIPPED: {exc}")
            continue
        print_backtest_report(result)
        results.append((label, outcome, result))

    print()
    print("=" * 88)
    print("R-45 SUMMARY — receiver_contention_window_score credibility")
    print("=" * 88)
    header = (
        f"  {'Ablation':<18} {'outcome':<16} {'n_train':>7} {'n_test':>6}  "
        f"{'cov_90':>6}  {'CRPS':>7}  {'credible':>8}  {'beta':>7}  [p05, p95]"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for label, outcome, result in results:
        credible, mean_beta, p05, p95 = _contention_credibility(result)
        credible_flag = "YES ***" if credible else "no"
        beta_str = f"{mean_beta:+.4f}" if mean_beta == mean_beta else "  n/a "
        ci_str = f"[{p05:+.3f}, {p95:+.3f}]" if p05 == p05 else "   n/a      "
        print(
            f"  {label:<18} {outcome:<16} {result.train_n:>7} {result.test_n:>6}  "
            f"{result.coverage_90:>6.1%}  {result.test_crps:>7.4f}  "
            f"{credible_flag:>8}  {beta_str:>7}  {ci_str}"
        )
    print()


if __name__ == "__main__":
    main()
