"""R-56: Contract-year selection bias flag ablation (#11 / ATT correction).

receiver_acquired_contract_year_pct = fraction of acquired players whose bWAR salary
record ends at the trade season (no next-season salary row). Proxy for "walk-year"
acquisitions where the player was motivated to perform / where the origin team was
motivated to sell before losing him for nothing.

Hypothesis: high contract-year pct → positive selection bias → acquired players
over-perform in the window (walk-year boost) OR negative bias if teams sell before
performance cliff. Direction is empirically ambiguous.

Tests on war_delta, kpct_delta, xwoba_delta.
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
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3,
    print_backtest_report,
)
from savage_trade_evaluator.modeling.v2.features import ACQUIRED_PLAYER_FEATURES

FEAT = "receiver_acquired_contract_year_pct"

OUTCOME_BASES: dict[str, tuple[str, ...]] = {
    "war_delta": V3_OUTCOME_FEATURES["war_delta"],
    "kpct_delta": V3_OUTCOME_FEATURES["kpct_delta"],
    "xwoba_delta": V3_OUTCOME_FEATURES["xwoba_delta"],
}


def _credibility(result, feature: str) -> tuple[bool, float, float, float, float]:
    row = result.credible_features[result.credible_features["feature"] == feature]
    if row.empty:
        return False, float("nan"), float("nan"), float("nan"), float("nan")
    r = row.iloc[0]
    return bool(r["credible"]), float(r["mean_beta"]), float(r["p05"]), float(r["p95"]), float(r["directional_mass"])


def main() -> None:
    print("Loading combined matrix…")
    combined = assemble_v3_combined()
    if FEAT not in combined.columns:
        print(f"ABORT: {FEAT} not in combined — check build_feature_matrix()")
        return

    fill = combined[FEAT].notna().mean()
    print(f"{FEAT} fill rate: {fill:.1%}")

    results = []
    for outcome, base_cols in OUTCOME_BASES.items():
        base_cols = tuple(c for c in base_cols if c in combined.columns)
        aug_cols = base_cols + (FEAT,)
        print(f"\n{'#' * 88}")
        print(f"# R-56: {outcome} + {FEAT}  ({len(aug_cols)} features)")
        print(f"{'#' * 88}")
        result = backtest_outcome_v3(outcome, feature_cols=aug_cols, combined=combined)
        print_backtest_report(result)
        credible, mean_b, p05, p95, mass = _credibility(result, FEAT)
        results.append((outcome, result, credible, mean_b, p05, p95, mass))

    print()
    print("=" * 88)
    print("R-56 SUMMARY — contract-year selection bias proxy")
    print("=" * 88)
    hdr = f"  {'outcome':<12} {'cov_90':>6}  {'CRPS':>8}  {'credible':>9}  {'beta':>7}  [p05, p95]  mass"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for outcome, result, credible, mean_b, p05, p95, mass in results:
        flag = "YES ***" if credible else "no"
        beta_str = f"{mean_b:+.4f}" if not np.isnan(mean_b) else "  n/a  "
        ci_str = f"[{p05:+.3f}, {p95:+.3f}]" if not np.isnan(p05) else "  n/a "
        mass_str = f"{mass:.0%}" if not np.isnan(mass) else " n/a"
        print(
            f"  {outcome:<12} {result.coverage_90:>6.1%}  {result.test_crps:>8.4f}"
            f"  {flag:>9}  {beta_str}  {ci_str}  {mass_str}"
        )


if __name__ == "__main__":
    main()
