"""R-51 — era-heteroscedastic sigma model for war_delta.

Confirmed cause of 97.9% coverage (target 90%): era variance shift.
Training std=2.23 vs test std=1.27 (1.76x). The flat-sigma model learns
sigma from a noisier pre-2021 era and over-widens CIs for post-2021 data.

Fix: sigma = exp(log_sigma_base + beta_sigma_era * post_2021)

Key diagnostic: if beta_sigma_era << 0 with high directional mass, the era
boundary is real and the heteroscedastic model should narrow coverage toward
the 90% target.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import os

import numpy as np

os.environ.setdefault(
    "STE_DUCKDB_PATH",
    "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db",
)

from savage_trade_evaluator.modeling.v3 import (  # noqa: E402
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3_heteroscedastic,
    print_backtest_report,
)

_FLAT_SIGMA_COVERAGE = 0.979
_ERA_CUTOFF = 2021


def _beta_sigma_era_summary(result) -> None:
    post = result.fit.trace.posterior
    v = post["beta_sigma_era"].values.reshape(-1)
    mean = float(v.mean())
    p05 = float(np.percentile(v, 5))
    p95 = float(np.percentile(v, 95))
    mass_neg = float((v < 0).mean())
    directional_mass = max(mass_neg, 1 - mass_neg)

    print("=" * 88)
    print("ERA-SIGMA DIAGNOSTIC (beta_sigma_era)")
    print("=" * 88)
    print(f"  mean: {mean:+.4f}   90% CI: [{p05:+.4f}, {p95:+.4f}]")
    print(f"  P(beta < 0): {mass_neg:.1%}   directional mass: {directional_mass:.1%}")
    if mean < 0 and mass_neg >= 0.90:
        print("  => post-2021 era is meaningfully quieter (expected)")
    elif mean < 0 and mass_neg >= 0.75:
        print("  => directional signal but weak; era effect is real but noisy")
    else:
        print("  => no strong directional signal; era boundary may not be the lever")
    print()


def main() -> None:
    combined = assemble_v3_combined()

    feature_cols = V3_OUTCOME_FEATURES["war_delta"]
    feature_cols = tuple(c for c in feature_cols if c in combined.columns)

    result = backtest_outcome_v3_heteroscedastic(
        outcome="war_delta",
        feature_cols=feature_cols,
        era_cutoff=_ERA_CUTOFF,
        combined=combined,
    )

    print_backtest_report(result)
    _beta_sigma_era_summary(result)

    print("=" * 88)
    print("COVERAGE COMPARISON")
    print("=" * 88)
    delta = result.coverage_90 - _FLAT_SIGMA_COVERAGE
    sign = "+" if delta >= 0 else ""
    print(f"  Flat-sigma baseline:      {_FLAT_SIGMA_COVERAGE:.1%}")
    print(f"  Heteroscedastic (R-51):   {result.coverage_90:.1%}   ({sign}{delta:.1%})")
    print(f"  Target:                    90.0%")
    if result.coverage_90 <= 0.93:
        print("  => PASS: coverage pulled toward target")
    else:
        print("  => STILL OVER-DISPERSED: heteroscedastic sigma alone insufficient")
    print()


if __name__ == "__main__":
    main()
