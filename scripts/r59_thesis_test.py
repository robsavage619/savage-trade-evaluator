"""R-59: Thesis test — player-quality-only vs full contextual model.

The core claim of this project (D-01 / NAIVE_BASELINE.md): knowing the receiving
team's development context — dev-fit scores, org jump metrics, payroll, alumni
network, platoon deployment — adds predictive value *beyond* knowing who the
player is.

Three models compared on the same walk-forward folds as R-57/R-58:

  1. Intercept-only (Bayesian, from R-58) — absolute floor
  2. Player-quality model: ACQUIRED_PLAYER_FEATURES only (13 features; no receiver
     team context). This is the "naive baseline" — I know who the player is but not
     where he's going.
  3. Full contextual model: ALL_FEATURES (23 features; includes receiver team context).
     This is the thesis model.

Skill score (contextual vs player-quality) > 0 confirms the thesis.
Skill score ≤ 0 means team context adds noise at the current sample size.

Pre-registered as D-41 in trade-eval--decisions.md before this script was run.
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
logger = logging.getLogger("r59")

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v2.backtest import _crps_empirical
from savage_trade_evaluator.modeling.v2.features import (
    ACQUIRED_PLAYER_FEATURES,
    ALL_FEATURES,
)
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    fit_v3,
    predict,
    _split_and_impute,
)
from savage_trade_evaluator.modeling.v3_cv import (
    MIN_TEST_N,
    walk_forward_splits,
)
sys.path.insert(0, str(Path(__file__).parent))
from r58_baseline_comparison import _fit_bayesian_intercept_only


def run_fold(
    outcome: str,
    combined: pd.DataFrame,
    train_end: int,
    test_end: int,
    train_start: int,
    min_n: int,
) -> dict:
    """One fold: intercept-only + player-quality + full-contextual CRPS."""
    all_cols = V3_OUTCOME_FEATURES[outcome]   # ALL_FEATURES for war_delta/dollar_surplus

    train_full, test_full = _split_and_impute(
        outcome, all_cols, train_end, test_end,
        combined=combined, train_start_season=train_start,
    )
    n_train = len(train_full)
    n_test = len(test_full)
    sufficient = n_test >= min_n
    y_test_full = test_full[outcome].to_numpy(float)

    # --- baseline: Bayesian intercept-only ---
    crps_intercept = float("nan")
    if n_train >= 50:
        crps_intercept = _fit_bayesian_intercept_only(train_full, test_full, outcome)

    # --- naive: player-quality features only (no receiver team context) ---
    # Use the subset of ACQUIRED_PLAYER_FEATURES that appear in all_cols.
    player_cols = tuple(c for c in ACQUIRED_PLAYER_FEATURES if c in all_cols)
    crps_player = float("nan")
    if n_train >= 50 and player_cols:
        train_p, test_p = _split_and_impute(
            outcome, player_cols, train_end, test_end,
            combined=combined, train_start_season=train_start,
            minimum_features_present=1,
        )
        if len(train_p) >= 50:
            fit_p = fit_v3(train_p, outcome, player_cols)
            preds_p = predict(fit_p, test_p)
            y_test_p = test_p[outcome].to_numpy(float)
            crps_player = _crps_empirical(y_test_p, preds_p)

    # --- full contextual model ---
    crps_full = float("nan")
    if n_train >= 50:
        fit_f = fit_v3(train_full, outcome, all_cols)
        preds_f = predict(fit_f, test_full)
        crps_full = _crps_empirical(y_test_full, preds_f)

    skill_full_vs_intercept = (
        1.0 - (crps_full / crps_intercept)
        if not np.isnan(crps_intercept) and crps_intercept
        else float("nan")
    )
    skill_player_vs_intercept = (
        1.0 - (crps_player / crps_intercept)
        if not np.isnan(crps_intercept) and crps_intercept
        else float("nan")
    )
    # THE THESIS SKILL SCORE: does team context beat player-quality alone?
    skill_full_vs_player = (
        1.0 - (crps_full / crps_player)
        if not np.isnan(crps_player) and crps_player
        else float("nan")
    )

    return {
        "outcome": outcome,
        "train_end": train_end,
        "test_end": test_end,
        "n_train": n_train,
        "n_test": n_test,
        "sufficient": sufficient,
        "n_player_features": len(player_cols),
        "n_context_features": len(all_cols) - len(player_cols),
        "crps_intercept": crps_intercept,
        "crps_player": crps_player,
        "crps_full": crps_full,
        "skill_full_vs_intercept": skill_full_vs_intercept,
        "skill_player_vs_intercept": skill_player_vs_intercept,
        "skill_full_vs_player": skill_full_vs_player,  # THESIS TEST
    }


def print_results(rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    outcomes = df["outcome"].unique()

    sep = "=" * 118
    print()
    print(sep)
    print("R-59 THESIS TEST: player-quality-only vs full contextual model")
    print("NAIVE = ACQUIRED_PLAYER_FEATURES only (no team context)")
    print("FULL  = ALL_FEATURES (team context added)")
    print("Thesis: skill(full/naive) > 0  →  team context adds predictive value beyond player quality")
    print(sep)

    for outcome in outcomes:
        sub = df[df["outcome"] == outcome].copy()
        sufficient = sub[sub["sufficient"]]
        n_pf = int(sub["n_player_features"].iloc[0])
        n_cf = int(sub["n_context_features"].iloc[0])
        print()
        print(f"  {outcome}  (naive={n_pf} player features, context_added={n_cf} team features)")
        print(f"  {'fold window':<15} {'n_test':>7} {'intercept':>10} {'naive':>10} {'full':>10}  "
              f"{'skill(full/int)':>15}  {'skill(naive/int)':>16}  {'skill(full/naive)':>17}")
        print("  " + "-" * 108)

        for _, r in sub.iterrows():
            suf = "" if r["sufficient"] else " INSUF"
            ci = f"{r['crps_intercept']:>10.4f}" if not np.isnan(r["crps_intercept"]) else "       n/a"
            cp = f"{r['crps_player']:>10.4f}" if not np.isnan(r["crps_player"]) else "       n/a"
            cf = f"{r['crps_full']:>10.4f}" if not np.isnan(r["crps_full"]) else "       n/a"
            s_fi = f"{r['skill_full_vs_intercept']:>+14.1%}" if not np.isnan(r["skill_full_vs_intercept"]) else "             n/a"
            s_pi = f"{r['skill_player_vs_intercept']:>+15.1%}" if not np.isnan(r["skill_player_vs_intercept"]) else "              n/a"
            s_fp = f"{r['skill_full_vs_player']:>+16.1%}" if not np.isnan(r["skill_full_vs_player"]) else "               n/a"
            print(f"  {r['test_end']-1}–{r['test_end']:<10} {r['n_test']:>7} {ci} {cp} {cf}  {s_fi}  {s_pi}  {s_fp}{suf}")

        if not sufficient.empty:
            print()
            agg_cols = ["crps_intercept", "crps_player", "crps_full",
                        "skill_full_vs_intercept", "skill_player_vs_intercept", "skill_full_vs_player"]
            agg = sufficient[agg_cols].mean()
            print(
                f"  Mean (sufficient):              "
                f"{agg['crps_intercept']:>10.4f} {agg['crps_player']:>10.4f} {agg['crps_full']:>10.4f}  "
                f"{agg['skill_full_vs_intercept']:>+14.1%}  {agg['skill_player_vs_intercept']:>+15.1%}  "
                f"{agg['skill_full_vs_player']:>+16.1%}"
            )
            # Verdict
            mean_skill = agg["skill_full_vs_player"]
            if mean_skill > 0.02:
                verdict = "THESIS SUPPORTED — team context beats player-quality-only by {:.1%}".format(mean_skill)
            elif mean_skill > 0.0:
                verdict = "WEAK SUPPORT — marginal gain ({:.1%}); likely within noise".format(mean_skill)
            elif mean_skill > -0.02:
                verdict = "PARITY — no detectable difference (skill={:.1%})".format(mean_skill)
            else:
                verdict = "THESIS NOT SUPPORTED — player-quality-alone beats full model by {:.1%}".format(-mean_skill)
            print(f"\n  VERDICT ({outcome}): {verdict}")

    print()
    print(sep)
    print("  skill(full/naive) > 0   → team context adds value; supports thesis (D-01)")
    print("  skill(full/naive) ≈ 0   → team context undetectable at this sample size")
    print("  skill(full/naive) < 0   → over-parameterized; player quality is sufficient")
    print("  skill(naive/int)  > 0   → player quality alone beats intercept; sanity check")
    print(sep)


def main() -> None:
    logger.info("Loading combined dataset...")
    combined = assemble_v3_combined()
    logger.info("combined: %d rows", len(combined))

    all_rows: list[dict] = []
    outcomes = ["war_delta", "dollar_surplus"]

    for outcome in outcomes:
        splits = walk_forward_splits(outcome, combined)
        min_n = MIN_TEST_N.get(outcome, 50)
        all_cols = V3_OUTCOME_FEATURES[outcome]
        player_n = sum(1 for c in ACQUIRED_PLAYER_FEATURES if c in all_cols)
        context_n = len(all_cols) - player_n
        logger.info(
            "%s: %d folds, player_features=%d, context_features=%d",
            outcome, len(splits), player_n, context_n,
        )

        for split in splits:
            logger.info("  %s", split.label)
            t0 = time.time()
            row = run_fold(
                outcome=outcome,
                combined=combined,
                train_end=split.train_end,
                test_end=split.test_end,
                train_start=split.train_start,
                min_n=min_n,
            )
            elapsed = time.time() - t0
            thesis = row["skill_full_vs_player"]
            logger.info(
                "    intercept=%.4f  naive=%.4f  full=%.4f  thesis_skill=%+.1f%%  (%.1fs)",
                row["crps_intercept"], row["crps_player"], row["crps_full"],
                (thesis * 100) if not np.isnan(thesis) else float("nan"), elapsed,
            )
            all_rows.append(row)

    print_results(all_rows)


if __name__ == "__main__":
    main()
