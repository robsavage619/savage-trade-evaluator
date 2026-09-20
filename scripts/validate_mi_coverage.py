# pyright: reportAttributeAccessIssue=false, reportReturnType=false, reportArgumentType=false
"""Part 2 of Step 9 revalidation: compare MI vs mean-imputation on the backtest test set.

For each production outcome:
1. Load the production fit (cached, no MCMC).
2. Assemble the raw (un-imputed) test set using the same temporal split as
   backtest_outcome_v3 (train_end=2020, test=2021-2024).
3. Score with two modes:
   - Mean-imputation (MI=False): fill NaN with production fit.feature_means, predict normally.
   - Multiple imputation (MI=True): pass raw NaN to predict(..., multiple_imputation=True).
4. Report overall + sparse-row (>=25% features missing) coverage-90 / MAE / CRPS.
5. Print a markdown table and append it to docs/revalidation/2026-07-post-mi.md.

GO criterion (from the plan):
  - Sparse rows: |coverage90 - 0.90| under MI <= |coverage90 - 0.90| under mean-imputation
  - MAE/CRPS degrade < 2% relative (overall) compared to mean-imputation baseline
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.production_fit import get_fit
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    _crps_empirical,  # type: ignore[attr-defined]
    assemble_v3_combined,
    predict,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BACKTEST_TRAIN_END = 2020  # matches backtest_outcome_v3 default
BACKTEST_TEST_END = 2024
MIN_FEATURES_PRESENT = 5
SPARSE_THRESHOLD = 0.25  # >=25% missing features = sparse row
CLIP_DOLLAR = 200e6


def _build_raw_test(outcome: str, cols: tuple[str, ...]) -> pd.DataFrame:
    """Return the raw (un-imputed) test rows with NaN intact."""
    combined = assemble_v3_combined()
    # Keep only rows where the outcome label exists and at least MIN_FEATURES_PRESENT features are present.
    combined = combined[combined[outcome].notna()].copy()
    present = combined[list(cols)].notna().sum(axis=1)
    combined = combined[present >= MIN_FEATURES_PRESENT].copy()

    test_mask = (combined["trade_season"] > BACKTEST_TRAIN_END) & (
        combined["trade_season"] <= BACKTEST_TEST_END
    )
    return combined[test_mask].reset_index(drop=True)


def _score_mode(
    test_raw: pd.DataFrame,
    outcome: str,
    cols: tuple[str, ...],
    mi: bool,
) -> dict[str, float]:
    """Score test_raw with mean-imputation (mi=False) or MI (mi=True)."""
    fit = get_fit(outcome)

    if mi:
        feat_df = test_raw[list(cols)].copy().astype("float64")
        pred_t = predict(fit, feat_df, multiple_imputation=True)
    else:
        # Mean-imputation baseline: fill NaN with fit.feature_means.
        feat_df = test_raw[list(cols)].copy().astype("float64")
        for c in cols:
            fill = float(fit.feature_means.get(c, 0.0))
            feat_df[c] = feat_df[c].fillna(fill)
        pred_t = predict(fit, feat_df, multiple_imputation=False)

    # The production fit (get_fit) trains on raw dollar values, with no signed-log transform.
    # _inv_signed_log only applies when scoring backtest fits that trained with the transform.
    pred = pred_t
    mean_pred = pred.mean(axis=1)
    crps = _crps_empirical(test_raw[outcome].to_numpy(dtype=float), pred)

    y_true = test_raw[outcome].to_numpy(dtype=float)
    mae = float(np.mean(np.abs(mean_pred - y_true)))
    p05 = np.percentile(pred, 5, axis=1)
    p95 = np.percentile(pred, 95, axis=1)
    cov90 = float(((y_true >= p05) & (y_true <= p95)).mean())

    return {"mae": mae, "crps": crps, "cov90": cov90}


def _sparse_mask(test_raw: pd.DataFrame, cols: tuple[str, ...]) -> np.ndarray:
    """Boolean row mask: True where at least SPARSE_THRESHOLD of the columns are NaN."""
    n_cols = len(cols)
    if n_cols == 0:
        return np.zeros(len(test_raw), dtype=bool)
    n_missing = test_raw[list(cols)].isna().sum(axis=1).to_numpy()
    return n_missing / n_cols >= SPARSE_THRESHOLD


def run(out_path: Path | None) -> None:
    outcomes = ("war_delta", "dollar_surplus", "surplus_wins")
    rows: list[dict] = []

    for outcome in outcomes:
        cols = V3_OUTCOME_FEATURES[outcome]
        logger.info("outcome=%s  n_features=%d", outcome, len(cols))

        test_raw = _build_raw_test(outcome, cols)
        sparse = _sparse_mask(test_raw, cols)
        n_total = len(test_raw)
        n_sparse = int(sparse.sum())
        logger.info(
            "  test rows: %d total  %d sparse (>=25%% missing)",
            n_total,
            n_sparse,
        )

        for mi_flag, label in [(False, "mean-imp"), (True, "MI")]:
            overall = _score_mode(test_raw, outcome, cols, mi=mi_flag)
            if n_sparse > 0:
                sparse_metrics = _score_mode(
                    test_raw[sparse].reset_index(drop=True), outcome, cols, mi=mi_flag
                )
            else:
                sparse_metrics = {"mae": float("nan"), "crps": float("nan"), "cov90": float("nan")}

            rows.append(
                {
                    "outcome": outcome,
                    "mode": label,
                    "n_total": n_total,
                    "n_sparse": n_sparse,
                    "overall_cov90": round(overall["cov90"], 4),
                    "overall_mae": round(overall["mae"], 4),
                    "overall_crps": round(overall["crps"], 4),
                    "sparse_cov90": round(sparse_metrics["cov90"], 4),
                    "sparse_mae": round(sparse_metrics["mae"], 4),
                    "sparse_crps": round(sparse_metrics["crps"], 4),
                }
            )

    df = pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Go/no-go verdict
    # ------------------------------------------------------------------
    verdict_lines: list[str] = []
    go = True
    for outcome in outcomes:
        mean_row = df[(df["outcome"] == outcome) & (df["mode"] == "mean-imp")].iloc[0]
        mi_row = df[(df["outcome"] == outcome) & (df["mode"] == "MI")].iloc[0]

        # Sparse coverage criterion
        sparse_dev_mean = abs(float(mean_row["sparse_cov90"]) - 0.90)
        sparse_dev_mi = abs(float(mi_row["sparse_cov90"]) - 0.90)
        if float(mean_row["n_sparse"]) > 0:
            cov_pass = sparse_dev_mi <= sparse_dev_mean
        else:
            cov_pass = True  # no sparse rows, so the criterion does not apply
            verdict_lines.append(f"  - {outcome}: no sparse rows, coverage criterion N/A")

        # MAE/CRPS degradation criterion (overall)
        baseline_mae = float(mean_row["overall_mae"])
        mi_mae = float(mi_row["overall_mae"])
        mae_degrade = (mi_mae - baseline_mae) / baseline_mae if baseline_mae > 0 else 0.0
        mae_pass = mae_degrade < 0.02

        baseline_crps = float(mean_row["overall_crps"])
        mi_crps = float(mi_row["overall_crps"])
        crps_degrade = (mi_crps - baseline_crps) / baseline_crps if baseline_crps > 0 else 0.0
        crps_pass = crps_degrade < 0.02

        outcome_go = cov_pass and mae_pass and crps_pass
        go = go and outcome_go
        verdict_lines.append(
            f"  - {outcome}: cov_pass={cov_pass} "
            f"(sparse |dev| mean={sparse_dev_mean:.4f} MI={sparse_dev_mi:.4f}), "
            f"mae_degrade={mae_degrade:+.2%} {'PASS' if mae_pass else 'FAIL'}, "
            f"crps_degrade={crps_degrade:+.2%} {'PASS' if crps_pass else 'FAIL'} "
            f"-> {'GO' if outcome_go else 'NO-GO'}"
        )

    overall_verdict = "**GO**" if go else "**NO-GO**"
    verdict_block = "\n".join([f"### Verdict: {overall_verdict}", "", *verdict_lines])

    # ------------------------------------------------------------------
    # Markdown table
    # ------------------------------------------------------------------
    md_lines = [
        "",
        "---",
        "",
        "## Part 2: MI coverage validation",
        "",
        f"Sparse threshold: at least {SPARSE_THRESHOLD:.0%} of features missing. "
        f"GO criteria: sparse |cov90 - 0.90| under MI no worse than mean-imp; "
        f"overall MAE/CRPS degrade <2%.",
        "",
        "| outcome | mode | n_total | n_sparse | overall_cov90 | overall_mae | overall_crps | sparse_cov90 | sparse_mae | sparse_crps |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for _, r in df.iterrows():
        md_lines.append(
            f"| {r['outcome']} | {r['mode']} | {r['n_total']} | {r['n_sparse']} "
            f"| {r['overall_cov90']} | {r['overall_mae']} | {r['overall_crps']} "
            f"| {r['sparse_cov90']} | {r['sparse_mae']} | {r['sparse_crps']} |"
        )
    md_lines += ["", verdict_block, ""]

    md = "\n".join(md_lines)
    print(md)

    if out_path is not None:
        with out_path.open("a") as f:
            f.write(md)
        logger.info("appended MI validation table to %s", out_path)

    if not go:
        import sys

        logger.error(
            "MI validation NO-GO. Do not label these as 'honest intervals' in the product surface."
        )
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validate MI coverage vs mean-imputation baseline."
    )
    parser.add_argument(
        "--out",
        default="docs/revalidation/2026-07-post-mi.md",
        help="Path to append markdown table to (default: docs/revalidation/2026-07-post-mi.md)",
    )
    args = parser.parse_args()
    run(Path(args.out))
