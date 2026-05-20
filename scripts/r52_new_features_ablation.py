"""R-52: Ablation of 3 new features — alumni network, tech adoption, sunk-cost trap.

Tests each new feature individually by adding it to the current credible
war_delta feature set and checking D-26 credibility (CI excludes zero AND
directional mass >= 95%).
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/"
    "gallant-cerf-24bd10/data/duckdb/trades.db",
)

from savage_trade_evaluator.modeling.v3 import (
    ALL_FEATURES,
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3,
    coefficient_summary,
    print_backtest_report,
)

NEW_FEATURES: tuple[str, ...] = (
    "receiver_alumni_network_score",
    "receiver_tech_adoption_lead_years",
    "origin_sunk_cost_pressure",
)


def _credibility(result, feature: str) -> tuple[bool, float, float, float]:
    row = result.credible_features[result.credible_features["feature"] == feature]
    if row.empty:
        return False, float("nan"), float("nan"), float("nan")
    r = row.iloc[0]
    return bool(r["credible"]), float(r["mean_beta"]), float(r["p05"]), float(r["p95"])


def main() -> None:
    print("Loading combined feature+outcome matrix…")
    combined = assemble_v3_combined()

    # Strip contract-year feature if not yet in DB
    base_cols = tuple(
        c for c in V3_OUTCOME_FEATURES["war_delta"]
        if c in combined.columns
    )

    results = []
    for feat in NEW_FEATURES:
        if feat not in combined.columns:
            print(f"\nSKIP {feat} — not in combined DataFrame")
            continue
        aug_cols = base_cols + (feat,)
        print(f"\n{'#' * 88}")
        print(f"# R-52: war_delta + {feat}  ({len(aug_cols)} features)")
        print(f"{'#' * 88}")
        result = backtest_outcome_v3(
            "war_delta",
            feature_cols=aug_cols,
            combined=combined,
        )
        print_backtest_report(result)
        credible, mean_b, p05, p95 = _credibility(result, feat)
        results.append((feat, result, credible, mean_b, p05, p95))

    print()
    print("=" * 88)
    print("R-52 SUMMARY — new feature D-26 credibility on war_delta")
    print("=" * 88)
    hdr = f"  {'Feature':<42} {'cov_90':>6}  {'CRPS':>7}  {'credible':>9}  {'beta':>7}  [p05, p95]"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for feat, result, credible, mean_b, p05, p95 in results:
        flag = "YES ***" if credible else "no"
        beta_str = f"{mean_b:+.4f}" if not np.isnan(mean_b) else "  n/a  "
        ci_str = f"[{p05:+.3f}, {p95:+.3f}]" if not np.isnan(p05) else "  n/a  "
        print(
            f"  {feat:<42} {result.coverage_90:>6.1%}  {result.test_crps:>7.4f}"
            f"  {flag:>9}  {beta_str}  {ci_str}"
        )


if __name__ == "__main__":
    main()
