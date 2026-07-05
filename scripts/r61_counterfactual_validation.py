"""R-61: C1a org-adjusted counterfactual validation — D-50 go/no-go.

Head-to-head walk-forward CV comparison of:
  - ``war_delta_residual`` (Marcel-adjusted, R-60 baseline: 9 confirmed features)
  - ``war_delta_cf`` (org-adjusted Marcel, C1a counterfactual)

The counterfactual strips both the aging signal AND the sending team's
development context. The hypothesis is that this tighter control surface
reveals more team-context signal for the receiving team.

Decision to file: D-50 (pending). The counterfactual goes to production iff:
  1. mean CRPS(cf) <= mean CRPS(residual) + CRPS_TOLERANCE, AND
  2. confirmed features in cf >= confirmed features in residual (≥9).

If both conditions hold: war_delta_cf promoted to supplementary alongside residual.
If CRPS fails: C1a is informative but not predictively superior; keep residual.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("r61")

import pandas as pd

from savage_trade_evaluator.modeling.experiment import write_manifest
from savage_trade_evaluator.modeling.v3 import V3_OUTCOME_FEATURES, assemble_v3_combined
from savage_trade_evaluator.modeling.v3_cv import (
    V3CVResult,
    backtest_outcome_v3_cv,
    print_cv_report,
)

CRPS_TOLERANCE = 0.05  # WAR — cf can be up to 0.05 worse and still "equal"
RESIDUAL_BASELINE_CONFIRMED = 9  # R-60 result; pass if cf matches or exceeds this


def run_cv(outcome: str, combined: pd.DataFrame) -> V3CVResult:
    feat = V3_OUTCOME_FEATURES["war_delta"]
    logger.info("=" * 70)
    logger.info("R-61  outcome=%s  n_features=%d", outcome, len(feat))
    logger.info("=" * 70)
    t0 = time.time()
    result = backtest_outcome_v3_cv(outcome=outcome, feature_cols=feat, combined=combined)
    logger.info("outcome=%s  done in %.1fs", outcome, time.time() - t0)
    return result


def head_to_head_report(residual: V3CVResult, cf: V3CVResult) -> None:
    sep = "=" * 80
    print()
    print(sep)
    print("R-61 COUNTERFACTUAL VALIDATION — D-50 GO/NO-GO")
    print(sep)

    res_n_confirmed = int(residual.feature_stability["confirmed"].sum())
    cf_n_confirmed = int(cf.feature_stability["confirmed"].sum())

    crps_delta = cf.mean_crps - residual.mean_crps

    print()
    print(f"  {'Metric':<30} {'war_delta_residual':>20} {'war_delta_cf':>16}")
    print(f"  {'-' * 30} {'-' * 20} {'-' * 16}")
    print(f"  {'mean CRPS (WAR)':<30} {residual.mean_crps:>20.4f} {cf.mean_crps:>16.4f}")
    print(f"  {'std CRPS (WAR)':<30} {residual.std_crps:>20.4f} {cf.std_crps:>16.4f}")

    res_cov = [fr.coverage_90 for fr in residual.fold_results if fr.sufficient]
    cf_cov = [fr.coverage_90 for fr in cf.fold_results if fr.sufficient]
    if res_cov and cf_cov:
        import numpy as np

        res_mean = float(np.mean(res_cov))
        cf_mean = float(np.mean(cf_cov))
        print(f"  {'mean coverage_90':<30} {res_mean:>20.1%} {cf_mean:>16.1%}")

    print(f"  {'confirmed features':<30} {res_n_confirmed:>20d} {cf_n_confirmed:>16d}")
    print(f"  {'n folds':<30} {len(residual.fold_results):>20d} {len(cf.fold_results):>16d}")
    print()

    print("  Fold detail:")
    print(f"  {'Fold':<12} {'residual CRPS':>15} {'cf CRPS':>10} {'Δ':>8}")
    print(f"  {'-' * 12} {'-' * 15} {'-' * 10} {'-' * 8}")
    for r_fold, cf_fold in zip(residual.fold_results, cf.fold_results, strict=False):
        delta = cf_fold.crps - r_fold.crps
        sign = "+" if delta >= 0 else ""
        row = f"  {r_fold.split.label:<12} {r_fold.crps:>15.4f} {cf_fold.crps:>10.4f}"
        print(f"{row} {sign}{delta:>7.4f}")
    print()

    res_confirmed = set(
        residual.feature_stability.loc[residual.feature_stability["confirmed"], "feature"]
    )
    cf_confirmed = set(cf.feature_stability.loc[cf.feature_stability["confirmed"], "feature"])
    both = res_confirmed & cf_confirmed
    res_only = res_confirmed - cf_confirmed
    cf_only = cf_confirmed - res_confirmed

    if both:
        print(f"  Confirmed in BOTH ({len(both)}): {', '.join(sorted(both))}")
    if res_only:
        print(f"  Only in residual ({len(res_only)}): {', '.join(sorted(res_only))}")
    if cf_only:
        print(f"  Only in counterfactual ({len(cf_only)}): {', '.join(sorted(cf_only))}")
    print()

    crps_ok = crps_delta <= CRPS_TOLERANCE
    feat_ok = cf_n_confirmed >= RESIDUAL_BASELINE_CONFIRMED

    print("  VERDICT")
    crps_verdict = "PASS" if crps_ok else "FAIL"
    feat_verdict = "PASS" if feat_ok else "FAIL"
    tol = CRPS_TOLERANCE
    print(f"    CRPS delta = {crps_delta:+.4f} WAR (tolerance ≤ {tol})  →  {crps_verdict}")
    baseline = RESIDUAL_BASELINE_CONFIRMED
    print(f"    confirmed features: {cf_n_confirmed} vs baseline={baseline}  →  {feat_verdict}")
    print()

    if crps_ok and feat_ok:
        print("  D-50 VERDICT: GO — war_delta_cf promoted to supplementary outcome")
        print("    bump MODEL_VERSION to v3.3 and re-warm production cache")
    elif crps_ok and not feat_ok:
        print("  D-50 VERDICT: SUPPLEMENTARY — cf CRPS ok but fewer confirmed features;")
        print("    C1a is directionally useful but doesn't improve signal density")
    else:
        print("  D-50 VERDICT: NO-GO — counterfactual does not improve on residual;")
        print("    war_delta_residual stays as the Marcel-adjusted supplementary outcome")

    print()
    print(sep)


def main() -> None:
    logger.info("Building org retention factors and counterfactual residuals...")
    logger.info("This takes ~3-5 min on first run (scans full bWAR history)")
    combined = assemble_v3_combined(
        include_marcel_residual=True,
        include_counterfactual=True,
    )
    n_residual = combined["war_delta_residual"].notna().sum()
    n_cf = combined["war_delta_cf"].notna().sum()
    logger.info(
        "combined: %d rows — war_delta_residual: %d, war_delta_cf: %d",
        len(combined),
        n_residual,
        n_cf,
    )

    write_manifest(
        "r61_counterfactual_validation",
        {
            "war_delta_residual": V3_OUTCOME_FEATURES["war_delta"],
            "war_delta_cf": V3_OUTCOME_FEATURES["war_delta"],
        },
        extra={
            "crps_tolerance": CRPS_TOLERANCE,
            "residual_baseline_confirmed": RESIDUAL_BASELINE_CONFIRMED,
        },
    )

    residual = run_cv("war_delta_residual", combined)
    print_cv_report(residual)

    cf = run_cv("war_delta_cf", combined)
    print_cv_report(cf)

    head_to_head_report(residual, cf)


if __name__ == "__main__":
    main()
