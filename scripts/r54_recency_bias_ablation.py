"""R-54 — Regime-aware recency-bias K-trajectory ablation.

R-49 found ``receiver_org_pitcher_k_jump_3yr`` (flat 3yr mean) decayed from
r=-0.62 (2015-17) to r=+0.05 (2022-24) on kpct_delta as the PITCHf/x
dev-strategy edge was competed away league-wide by ~2021.

R-54 replaces the flat 3yr mean with an exponentially-weighted 5yr version
(half-life=2yr) and adds ``org_pitcher_k_jump_recency_bias`` = ewma − flat,
which captures whether an org is a *current* innovator vs. coasting.

This ablation:
  1. Runs backtest_outcome_v3("kpct_delta") augmented with recency_bias.
  2. Reports D-26 credibility for receiver_org_pitcher_k_jump_recency_bias.
  3. Compares CRPS against the R-43 kpct_delta baseline (~30 CRPS).
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db",
)

import argparse

from savage_trade_evaluator.modeling.v2.features import ACQUIRED_PLAYER_FEATURES
from savage_trade_evaluator.modeling.v3 import backtest_outcome_v3, print_backtest_report

# Baseline: kpct_delta R-43 credible features (CRPS ≈ 30)
_BASELINE_CRPS = 30.0

_RECENCY_FEATURE = "receiver_org_pitcher_k_jump_recency_bias"
_FEATURE_COLS = ACQUIRED_PLAYER_FEATURES + (_RECENCY_FEATURE,)


def _section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def run_ablation(run_mcmc: bool) -> None:
    """Run the full R-54 ablation."""
    _section("R-54 — Recency-bias K-trajectory ablation (kpct_delta)")

    if not run_mcmc:
        print("\n  SKIPPED — pass --run-mcmc to execute MCMC fit.\n")
        print(f"  Feature set ({len(_FEATURE_COLS)} features):")
        for f in _FEATURE_COLS:
            marker = " <-- NEW" if f == _RECENCY_FEATURE else ""
            print(f"    {f}{marker}")
        return

    print(f"\n  Running backtest on kpct_delta with {len(_FEATURE_COLS)} features ...")
    result = backtest_outcome_v3("kpct_delta", feature_cols=_FEATURE_COLS)
    print_backtest_report(result)

    _section("D-26 Credibility — receiver_org_pitcher_k_jump_recency_bias")

    credible = getattr(result, "credible_features", {})
    if _RECENCY_FEATURE in credible:
        direction = credible[_RECENCY_FEATURE]
        print(f"\n  {_RECENCY_FEATURE}: {direction}")
        print("  >>> D-26 CREDIBLE — recency bias is directionally consistent.")
    else:
        all_feats = getattr(result, "feature_credibility", {})
        if _RECENCY_FEATURE in all_feats:
            mass = all_feats[_RECENCY_FEATURE]
            print(f"\n  {_RECENCY_FEATURE}: directional mass = {mass:.3f}")
            if mass >= 0.9 or mass <= 0.1:
                print("  >>> D-26 CREDIBLE (|mass − 0.5| ≥ 0.4).")
            else:
                print("  >>> NOT credible at D-26 threshold.")
        else:
            print(f"\n  '{_RECENCY_FEATURE}' not found in result credibility dict.")
            print("  Check that compute_all() has been re-run to populate the new column.")

    _section("CRPS comparison vs R-43 baseline")

    crps = getattr(result, "crps", None)
    if crps is not None:
        delta = crps - _BASELINE_CRPS
        direction = "improvement" if delta < 0 else "degradation"
        print(f"\n  baseline CRPS (R-43) : {_BASELINE_CRPS:.1f}")
        print(f"  R-54 CRPS            : {crps:.3f}")
        print(f"  delta                : {delta:+.3f}  ({direction})")
    else:
        print("\n  CRPS not available in result object.")


def main() -> None:
    parser = argparse.ArgumentParser(description="R-54 recency-bias K-trajectory ablation")
    parser.add_argument(
        "--run-mcmc",
        action="store_true",
        default=False,
        help="Execute MCMC fit (slow). Without this flag, only prints the feature set.",
    )
    args = parser.parse_args()
    run_ablation(run_mcmc=args.run_mcmc)


if __name__ == "__main__":
    main()
