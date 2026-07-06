"""Baseline and post-change revalidation for V3.2 production model.

Runs backtest_outcome_v3 (single-split) + backtest_outcome_v3_cv (walk-forward)
for ("war_delta", "dollar_surplus", "surplus_wins") and emits a markdown table.

Usage:
    uv run python scripts/revalidate_v32.py --label baseline --out docs/revalidation/2026-07-baseline.md
    uv run python scripts/revalidate_v32.py --label post-mi  --out docs/revalidation/2026-07-post-mi.md

IMPORTANT: this script is READ-ONLY with respect to data/model_cache.
Never pass force_retrain=True; never reduce draws/tune. Expect hours of MCMC.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("revalidate_v32")

import pandas as pd

from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    backtest_outcome_v3,
)
from savage_trade_evaluator.modeling.v3_cv import backtest_outcome_v3_cv

OUTCOMES = ("war_delta", "dollar_surplus", "surplus_wins")
# Single-split defaults mirror production_fit.py (train_end_season=2022 for production,
# but backtest uses 2020 by default to keep a larger test window).
BACKTEST_TRAIN_END = 2020
BACKTEST_TEST_END = 2024


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def run_single_split(outcome: str, combined: pd.DataFrame) -> dict[str, float | int | str]:
    logger.info("single-split backtest: outcome=%s", outcome)
    t0 = time.time()
    result = backtest_outcome_v3(
        outcome,
        train_end_season=BACKTEST_TRAIN_END,
        test_end_season=BACKTEST_TEST_END,
        combined=combined,
    )
    elapsed = time.time() - t0
    logger.info(
        "  outcome=%s  train_n=%d  test_n=%d  MAE=%.4f  CRPS=%.4f  cov90=%.1f%%  elapsed=%.1fs",
        outcome,
        result.train_n,
        result.test_n,
        result.test_mae,
        result.test_crps,
        result.coverage_90 * 100,
        elapsed,
    )
    credible_count = int(result.credible_features["credible"].sum())
    return {
        "outcome": outcome,
        "train_n": result.train_n,
        "test_n": result.test_n,
        "test_mae": round(result.test_mae, 4),
        "test_crps": round(result.test_crps, 4),
        "coverage_90": round(result.coverage_90, 4),
        "credible_features": credible_count,
        "elapsed_s": round(elapsed, 1),
    }


def run_cv(outcome: str, combined: pd.DataFrame) -> dict[str, float | str]:
    logger.info("walk-forward CV: outcome=%s", outcome)
    t0 = time.time()
    try:
        result = backtest_outcome_v3_cv(
            outcome=outcome,
            feature_cols=V3_OUTCOME_FEATURES[outcome],
            combined=combined,
        )
        elapsed = time.time() - t0
        logger.info(
            "  outcome=%s  n_folds=%d  mean_CRPS=%.4f  std_CRPS=%.4f  elapsed=%.1fs",
            outcome,
            len(result.fold_results),
            result.mean_crps,
            result.std_crps,
            elapsed,
        )
        confirmed = (
            int(result.feature_stability["confirmed"].sum())
            if not result.feature_stability.empty
            else 0
        )
        return {
            "outcome": outcome,
            "n_folds": len(result.fold_results),
            "mean_crps": round(result.mean_crps, 4),
            "std_crps": round(result.std_crps, 4),
            "confirmed_features": confirmed,
            "exploratory_flag": result.exploratory_flag,
            "elapsed_s": round(elapsed, 1),
            "error": "",
        }
    except Exception as exc:
        elapsed = time.time() - t0
        logger.warning("CV failed for %s: %s", outcome, exc)
        return {
            "outcome": outcome,
            "n_folds": 0,
            "mean_crps": float("nan"),
            "std_crps": float("nan"),
            "confirmed_features": 0,
            "exploratory_flag": True,
            "elapsed_s": round(elapsed, 1),
            "error": str(exc),
        }


def render_markdown(
    label: str,
    sha: str,
    date_str: str,
    single_rows: list[dict],
    cv_rows: list[dict],
) -> str:
    lines: list[str] = []
    lines.append(f"# V3.2 Revalidation — {label}")
    lines.append("")
    lines.append(f"**Git SHA:** `{sha}`  **Date:** {date_str}")
    lines.append("")
    lines.append("## Single-split backtest")
    lines.append(
        f"Train through {BACKTEST_TRAIN_END}, test {BACKTEST_TRAIN_END + 1}–{BACKTEST_TEST_END}."
    )
    lines.append("")
    lines.append("| Outcome | train_n | test_n | MAE | CRPS | 90% coverage | credible_features |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in single_rows:
        cov_pct = (
            f"{r['coverage_90'] * 100:.1f}%"
            if isinstance(r["coverage_90"], float)
            else r["coverage_90"]
        )
        lines.append(
            f"| {r['outcome']} | {r['train_n']} | {r['test_n']} "
            f"| {r['test_mae']} | {r['test_crps']} | {cov_pct} | {r['credible_features']} |"
        )
    lines.append("")
    lines.append("## Walk-forward CV")
    lines.append("")
    lines.append(
        "| Outcome | n_folds | mean_CRPS | std_CRPS | confirmed_features | exploratory | error |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for r in cv_rows:
        exp = "yes" if r["exploratory_flag"] else "no"
        err = str(r.get("error") or "")
        lines.append(
            f"| {r['outcome']} | {r['n_folds']} | {r['mean_crps']} "
            f"| {r['std_crps']} | {r['confirmed_features']} | {exp} | {err} |"
        )
    lines.append("")
    lines.append("## Acceptance criteria (D-38)")
    lines.append("")
    lines.append("- **Go**: all three outcomes have `coverage_90 >= 0.80` (grade B or better).")
    lines.append("- **Stop**: any outcome below 0.80 — do NOT retrain or tweak; record and report.")
    lines.append("")
    lines.append(
        "Coverage grades: A ≥ 0.80, B ≥ 0.60, C ≥ 0.40, D < 0.40 "
        "(note: plan uses A≥0.8 threshold; single-split 90% CI should be near 0.90 if well-calibrated)."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="V3.2 revalidation script")
    parser.add_argument(
        "--label", default="baseline", help="Label for this run (e.g. baseline, post-mi)"
    )
    parser.add_argument("--out", type=Path, default=None, help="Output markdown file path")
    args = parser.parse_args()

    from savage_trade_evaluator.config import configure_logging

    configure_logging()

    sha = _git_sha()
    import datetime

    date_str = datetime.date.today().isoformat()

    logger.info("=== V3.2 revalidation: label=%s  sha=%s  date=%s ===", args.label, sha, date_str)
    logger.info("Loading combined dataset…")
    combined = assemble_v3_combined()
    logger.info("Combined: %d rows", len(combined))

    logger.info("--- Single-split backtests ---")
    single_rows = [run_single_split(o, combined) for o in OUTCOMES]

    logger.info("--- Walk-forward CV ---")
    cv_outcomes = ("war_delta", "dollar_surplus")
    cv_rows = [run_cv(o, combined) for o in cv_outcomes]
    # surplus_wins CV: attempt, capture fold-sparsity errors gracefully
    cv_rows.append(run_cv("surplus_wins", combined))

    md = render_markdown(args.label, sha, date_str, single_rows, cv_rows)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md)
        logger.info("wrote %s", args.out)
    else:
        print(md)

    logger.info("=== revalidation complete ===")


if __name__ == "__main__":
    main()
