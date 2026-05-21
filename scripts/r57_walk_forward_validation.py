"""R-57: Walk-forward CV re-validation of all pre-protocol 'confirmed' features.

Runs backtest_outcome_v3_cv() on all four outcomes using their current
V3_OUTCOME_FEATURES sets. This is the authoritative pass that decides whether
features claimed credible under the old single-split standard (R-01→R-56) survive
the new walk-forward bar (EXPERIMENT_PROTOCOL.md).

Results replace the single-split credibility claims. Features that fail the
walk-forward bar are demoted from CONFIRMED to EXPLORATORY.

Decision to file: D-37 (walk-forward CV as new standard), supersedes D-26.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("r57")

import pandas as pd

from savage_trade_evaluator.modeling.v3 import V3_OUTCOME_FEATURES, assemble_v3_combined
from savage_trade_evaluator.modeling.v3_cv import (
    V3CVResult,
    backtest_outcome_v3_cv,
    print_cv_report,
)


def run_outcome(
    outcome: str,
    combined: pd.DataFrame,
) -> V3CVResult:
    logger.info("=" * 70)
    logger.info("R-57  outcome=%s  n_features=%d", outcome, len(V3_OUTCOME_FEATURES[outcome]))
    logger.info("=" * 70)
    t0 = time.time()
    result = backtest_outcome_v3_cv(
        outcome=outcome,
        feature_cols=V3_OUTCOME_FEATURES[outcome],
        combined=combined,
    )
    elapsed = time.time() - t0
    logger.info("outcome=%s  done in %.1fs", outcome, elapsed)
    return result


def summarize_verdicts(results: dict[str, V3CVResult]) -> None:
    sep = "=" * 92
    print()
    print(sep)
    print("R-57 WALK-FORWARD VALIDATION — FINAL VERDICTS")
    print("(Features that pass: CONFIRMED | Fail: EXPLORATORY)")
    print(sep)

    for outcome, result in results.items():
        stability = result.feature_stability.copy()
        n_confirmed = stability["confirmed"].sum()
        n_exploratory = len(stability) - n_confirmed
        print()
        print(f"  {outcome}  ({len(result.fold_results)} folds, mean_CRPS={result.mean_crps:.4f} ± {result.std_crps:.4f})")
        if result.exploratory_flag:
            print("    *** EXPLORATORY FLAG: one or more folds n_test < 50 ***")

        # Confirmed
        confirmed = stability[stability["confirmed"]]
        if not confirmed.empty:
            print(f"    CONFIRMED ({len(confirmed)}):")
            for _, row in confirmed.iterrows():
                print(
                    f"      ✓ {row['feature']:<48}  "
                    f"credible {row['n_credible_folds']}/{row['n_sufficient_folds']} folds  "
                    f"median_β={row['median_beta']:+.4f}"
                )
        else:
            print("    CONFIRMED: none")

        # Exploratory (credible in at least 1 fold but not enough)
        partial = stability[~stability["confirmed"] & (stability["n_credible_folds"] > 0)]
        if not partial.empty:
            print(f"    EXPLORATORY — partial credibility ({len(partial)}):")
            for _, row in partial.iterrows():
                sign_note = "⚠ sign flip" if not row["consistent_sign"] else ""
                print(
                    f"      ~ {row['feature']:<48}  "
                    f"credible {row['n_credible_folds']}/{row['n_sufficient_folds']} folds  "
                    f"needed {row['n_needed']}  {sign_note}"
                )

        # Null (never credible)
        null_f = stability[stability["n_credible_folds"] == 0]
        if not null_f.empty:
            null_names = ", ".join(null_f["feature"].tolist())
            print(f"    NULL ({len(null_f)}): {null_names}")

    print()
    print(sep)
    print("Next steps:")
    print("  1. Update V3_OUTCOME_FEATURES to only include CONFIRMED features.")
    print("  2. File D-37 in decisions.md recording this as the new standard.")
    print("  3. Demote EXPLORATORY/NULL features to 'hypothesis-generating only'.")
    print(sep)


def main() -> None:
    logger.info("Loading combined dataset...")
    combined = assemble_v3_combined()
    logger.info("combined: %d rows, %d cols", len(combined), len(combined.columns))

    # Run all four outcomes. war_delta and dollar_surplus run with ALL_FEATURES (~16).
    # xwoba_delta and kpct_delta use the acquired-player-only subsets.
    outcomes = ["war_delta", "xwoba_delta", "kpct_delta", "dollar_surplus"]

    results: dict[str, V3CVResult] = {}
    for outcome in outcomes:
        try:
            result = run_outcome(outcome, combined)
            results[outcome] = result
            print_cv_report(result)
        except Exception:
            logger.exception("outcome=%s failed — continuing with remaining", outcome)

    if results:
        summarize_verdicts(results)
    else:
        logger.error("All outcomes failed — nothing to summarize.")
        sys.exit(1)


if __name__ == "__main__":
    main()
