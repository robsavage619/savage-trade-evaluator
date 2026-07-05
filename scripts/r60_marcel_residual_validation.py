"""R-60: Marcel residual outcome validation — D-49 go/no-go.

Head-to-head walk-forward CV comparison of ``war_delta`` (raw) vs
``war_delta_residual`` (Marcel-adjusted). The residual strips the
"player was going to age/decline anyway" component and isolates variation
attributable to the receiving team's development context.

Decision to file: D-49. The residual goes to production iff:
  1. mean CRPS(residual) <= mean CRPS(raw) + 0.05 WAR tolerance, AND
  2. residual has >= as many confirmed features as raw.

If both conditions hold: residual replaces raw as the primary war outcome.
If condition 1 holds but feature count drops: file as supplementary, not primary.
If condition 1 fails: residual is exploratory; raw stays primary.
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
logger = logging.getLogger("r60")

import pandas as pd

from savage_trade_evaluator.modeling.experiment import write_manifest
from savage_trade_evaluator.modeling.v3 import V3_OUTCOME_FEATURES, assemble_v3_combined
from savage_trade_evaluator.modeling.v3_cv import (
    V3CVResult,
    backtest_outcome_v3_cv,
    print_cv_report,
)

CRPS_TOLERANCE = 0.05  # WAR — residual can be up to 0.05 worse and still "equal"


def run_cv(outcome: str, combined: pd.DataFrame) -> V3CVResult:
    feat = V3_OUTCOME_FEATURES["war_delta"]  # same feature set for both outcomes
    logger.info("=" * 70)
    logger.info("R-60  outcome=%s  n_features=%d", outcome, len(feat))
    logger.info("=" * 70)
    t0 = time.time()
    result = backtest_outcome_v3_cv(outcome=outcome, feature_cols=feat, combined=combined)
    logger.info("outcome=%s  done in %.1fs", outcome, time.time() - t0)
    return result


def head_to_head_report(raw: V3CVResult, residual: V3CVResult) -> None:
    sep = "=" * 80
    print()
    print(sep)
    print("R-60 MARCEL RESIDUAL VALIDATION — D-49 GO/NO-GO")
    print(sep)

    raw_n_confirmed = int(raw.feature_stability["confirmed"].sum())
    res_n_confirmed = int(residual.feature_stability["confirmed"].sum())

    crps_delta = residual.mean_crps - raw.mean_crps

    print()
    print(f"  {'Metric':<30} {'war_delta (raw)':>18} {'war_delta_residual':>20}")
    print(f"  {'-' * 30} {'-' * 18} {'-' * 20}")
    print(f"  {'mean CRPS (WAR)':<30} {raw.mean_crps:>18.4f} {residual.mean_crps:>20.4f}")
    print(f"  {'std CRPS (WAR)':<30} {raw.std_crps:>18.4f} {residual.std_crps:>20.4f}")

    # Coverage per fold
    raw_cov = [fr.coverage_90 for fr in raw.fold_results if fr.sufficient]
    res_cov = [fr.coverage_90 for fr in residual.fold_results if fr.sufficient]
    if raw_cov and res_cov:
        import numpy as np

        raw_mean = float(np.mean(raw_cov))
        res_mean = float(np.mean(res_cov))
        print(f"  {'mean coverage_90':<30} {raw_mean:>18.1%} {res_mean:>20.1%}")

    print(f"  {'confirmed features':<30} {raw_n_confirmed:>18d} {res_n_confirmed:>20d}")
    print(f"  {'n folds':<30} {len(raw.fold_results):>18d} {len(residual.fold_results):>20d}")
    print()

    # Fold-level detail
    print("  Fold detail:")
    print(f"  {'Fold':<12} {'raw CRPS':>12} {'residual CRPS':>15} {'Δ':>8}")
    print(f"  {'-' * 12} {'-' * 12} {'-' * 15} {'-' * 8}")
    for r_fold, res_fold in zip(raw.fold_results, residual.fold_results, strict=False):
        delta = res_fold.crps - r_fold.crps
        sign = "+" if delta >= 0 else ""
        row = f"  {r_fold.split.label:<12} {r_fold.crps:>12.4f} {res_fold.crps:>15.4f}"
        print(f"{row} {sign}{delta:>7.4f}")
    print()

    # Confirmed features: show which are consistent across both
    raw_confirmed = set(raw.feature_stability.loc[raw.feature_stability["confirmed"], "feature"])
    res_confirmed = set(
        residual.feature_stability.loc[residual.feature_stability["confirmed"], "feature"]
    )
    both = raw_confirmed & res_confirmed
    raw_only = raw_confirmed - res_confirmed
    res_only = res_confirmed - raw_confirmed

    if both:
        print(f"  Confirmed in BOTH ({len(both)}): {', '.join(sorted(both))}")
    if raw_only:
        print(f"  Only in raw ({len(raw_only)}): {', '.join(sorted(raw_only))}")
    if res_only:
        print(f"  Only in residual ({len(res_only)}): {', '.join(sorted(res_only))}")
    print()

    # Verdict
    crps_ok = crps_delta <= CRPS_TOLERANCE
    feat_ok = res_n_confirmed >= raw_n_confirmed

    print("  VERDICT")
    crps_verdict = "PASS" if crps_ok else "FAIL"
    feat_verdict = "PASS" if feat_ok else "FAIL"
    tol = CRPS_TOLERANCE
    print(f"    CRPS delta = {crps_delta:+.4f} WAR (tolerance ≤ {tol})  →  {crps_verdict}")
    print(f"    confirmed features: {res_n_confirmed} vs {raw_n_confirmed}  →  {feat_verdict}")
    print()

    if crps_ok and feat_ok:
        print("  D-49 VERDICT: GO — war_delta_residual to production as primary war outcome")
    elif crps_ok and not feat_ok:
        print("  D-49 VERDICT: SUPPLEMENTARY — residual CRPS ok but fewer confirmed features;")
        print("    add as secondary outcome, keep war_delta as primary")
    else:
        print("  D-49 VERDICT: NO-GO — residual does not improve predictive performance;")
        print("    war_delta stays primary; war_delta_residual remains exploratory")

    print()
    print(sep)


def main() -> None:
    logger.info("Loading combined dataset (with Marcel residuals)...")
    combined = assemble_v3_combined(include_marcel_residual=True)
    n_residual = combined["war_delta_residual"].notna().sum()
    logger.info(
        "combined: %d rows, %d cols — %d rows have war_delta_residual",
        len(combined),
        len(combined.columns),
        n_residual,
    )

    write_manifest(
        "r60_marcel_residual_validation",
        {
            "war_delta": V3_OUTCOME_FEATURES["war_delta"],
            "war_delta_residual": V3_OUTCOME_FEATURES["war_delta"],
        },
        extra={"crps_tolerance": CRPS_TOLERANCE},
    )

    raw = run_cv("war_delta", combined)
    print_cv_report(raw)

    residual = run_cv("war_delta_residual", combined)
    print_cv_report(residual)

    head_to_head_report(raw, residual)


if __name__ == "__main__":
    main()
