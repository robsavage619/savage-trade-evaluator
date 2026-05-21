"""R-55: Ablate Retrosheet leverage + platoon features on all four outcomes.

Two new RECEIVER_TEAM_FEATURES materialized from Retrosheet event logs (#6, #7):
  receiver_reliever_leverage_ge_1_5_pct — fraction of reliever PAs in high-LI (≥1.5) situations
  receiver_platoon_woba_diff            — opp-hand wOBA minus same-hand wOBA (positive = platoon skill)

Tests each on:
  war_delta       — using V3_OUTCOME_FEATURES["war_delta"] base
  kpct_delta      — using ACQUIRED_PLAYER_FEATURES base (player-only, per R-35)
  xwoba_delta     — using ACQUIRED_PLAYER_FEATURES base
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

NEW_FEATURES = (
    "receiver_reliever_leverage_ge_1_5_pct",
    "receiver_platoon_woba_diff",
)

# war_delta uses ALL_FEATURES; kpct/xwoba use player-only subset (R-35 finding).
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
    print(f"Combined shape: {combined.shape}")

    results = []
    for outcome, base_cols in OUTCOME_BASES.items():
        base_cols = tuple(c for c in base_cols if c in combined.columns)
        for feat in NEW_FEATURES:
            if feat not in combined.columns:
                print(f"\nSKIP {feat} — not in combined")
                continue
            aug_cols = base_cols + (feat,)
            print(f"\n{'#' * 88}")
            print(f"# R-55: {outcome} + {feat}  ({len(aug_cols)} features)")
            print(f"{'#' * 88}")
            result = backtest_outcome_v3(outcome, feature_cols=aug_cols, combined=combined)
            print_backtest_report(result)
            credible, mean_b, p05, p95, mass = _credibility(result, feat)
            results.append((outcome, feat, result, credible, mean_b, p05, p95, mass))

    print()
    print("=" * 100)
    print("R-55 SUMMARY — Retrosheet leverage + platoon features")
    print("=" * 100)
    hdr = f"  {'outcome':<12} {'feature':<42} {'cov_90':>6}  {'CRPS':>8}  {'cred':>7}  {'beta':>7}  [p05, p95]  mass"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for outcome, feat, result, credible, mean_b, p05, p95, mass in results:
        flag = "YES ***" if credible else "no"
        beta_str = f"{mean_b:+.4f}" if not np.isnan(mean_b) else "  n/a  "
        ci_str = f"[{p05:+.3f}, {p95:+.3f}]" if not np.isnan(p05) else "  n/a "
        mass_str = f"{mass:.0%}" if not np.isnan(mass) else " n/a"
        print(
            f"  {outcome:<12} {feat:<42} {result.coverage_90:>6.1%}  {result.test_crps:>8.4f}"
            f"  {flag:>7}  {beta_str}  {ci_str}  {mass_str}"
        )


if __name__ == "__main__":
    main()
