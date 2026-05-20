"""R-53: Ablate 4 new pipeline features on kpct_delta and xwoba_delta.

R-52 tested these on war_delta — all null. kpct_delta and xwoba_delta use
ACQUIRED_PLAYER_FEATURES only (player-only subset per R-35), so the question
is whether any of the 4 new features add signal on the outcomes where team
context was previously excluded.

Features under test:
- receiver_alumni_network_score
- receiver_tech_adoption_lead_years
- origin_sunk_cost_pressure
- receiver_acquired_contract_year_pct  (if in combined)
"""

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/"
    "gallant-cerf-24bd10/data/duckdb/trades.db",
)

from savage_trade_evaluator.modeling.v3 import (
    ACQUIRED_PLAYER_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3,
    print_backtest_report,
)

NEW_FEATURES: tuple[str, ...] = (
    "receiver_alumni_network_score",
    "receiver_tech_adoption_lead_years",
    "origin_sunk_cost_pressure",
    "receiver_acquired_contract_year_pct",
)

OUTCOMES: tuple[str, ...] = ("kpct_delta", "xwoba_delta")


def _credibility(result, feature: str) -> tuple[bool, float, float, float]:
    row = result.credible_features[result.credible_features["feature"] == feature]
    if row.empty:
        return False, float("nan"), float("nan"), float("nan")
    r = row.iloc[0]
    return bool(r["credible"]), float(r["mean_beta"]), float(r["p05"]), float(r["p95"])


def main() -> None:
    print("Loading combined feature+outcome matrix…")
    combined = assemble_v3_combined()

    available_new = tuple(f for f in NEW_FEATURES if f in combined.columns)
    print(f"Available new features: {available_new}")

    base_cols = tuple(c for c in ACQUIRED_PLAYER_FEATURES if c in combined.columns)

    results = []
    for outcome in OUTCOMES:
        for feat in available_new:
            aug_cols = base_cols + (feat,)
            print(f"\n{'#' * 88}")
            print(f"# R-53: {outcome} + {feat}  ({len(aug_cols)} features)")
            print(f"{'#' * 88}")
            try:
                result = backtest_outcome_v3(
                    outcome,
                    feature_cols=aug_cols,
                    combined=combined,
                )
            except ValueError as e:
                print(f"  SKIPPED: {e}")
                results.append((outcome, feat, None, False, float("nan"), float("nan"), float("nan")))
                continue
            print_backtest_report(result)
            credible, mean_b, p05, p95 = _credibility(result, feat)
            results.append((outcome, feat, result, credible, mean_b, p05, p95))

    print()
    print("=" * 96)
    print("R-53 SUMMARY — new features on kpct_delta / xwoba_delta")
    print("=" * 96)
    hdr = f"  {'outcome':<14} {'feature':<42} {'cov_90':>6}  {'CRPS':>8}  {'credible':>9}  {'beta':>7}  [p05, p95]"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for outcome, feat, result, credible, mean_b, p05, p95 in results:
        flag = "YES ***" if credible else "no"
        beta_str = f"{mean_b:+.4f}" if not np.isnan(mean_b) else "   n/a "
        ci_str = f"[{p05:+.3f}, {p95:+.3f}]" if not np.isnan(p05) else "   n/a "
        cov = f"{result.coverage_90:.1%}" if result else "  n/a"
        crps = f"{result.test_crps:.4f}" if result else "   n/a"
        print(
            f"  {outcome:<14} {feat:<42} {cov:>6}  {crps:>8}"
            f"  {flag:>9}  {beta_str}  {ci_str}"
        )


if __name__ == "__main__":
    main()
