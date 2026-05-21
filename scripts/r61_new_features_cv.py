"""R-61–R-64: Walk-forward CV for four new features from 2025 trade failure analysis.

Tests each feature for credibility (posterior mass ≥ 97.5%, CI excludes zero)
across 5 walk-forward folds for war_delta and dollar_surplus.

D-42: receiver_acquired_origin_ytd_war — within-season WAR with origin team
D-43: receiver_devfit_x_peak_age — dev_fit_hitting × max(0, 32 − avg_age)
D-44: receiver_acquired_war_acceleration — WAR second derivative
D-45: receiver_park_factor_3yr — 3-year rolling park factor for receiving team

Each feature is tested in the full 27-feature model context (27 = prior 23 + 4 new).
Protocol: pre-registered before implementation (D-42–D-45 in decisions.md).
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

import numpy as np
import pandas as pd
import pymc as pm

from savage_trade_evaluator.modeling.v2.features import ALL_FEATURES
from savage_trade_evaluator.modeling.v3 import (
    assemble_v3_combined,
    _split_and_impute,
)
from savage_trade_evaluator.modeling.v3_cv import (
    CV_MASS_THRESHOLD,
    MIN_TEST_N,
    walk_forward_splits,
)

# Four new candidate features being tested
NEW_FEATURES: tuple[str, ...] = (
    "receiver_acquired_origin_ytd_war",   # D-42
    "receiver_devfit_x_peak_age",          # D-43
    "receiver_acquired_war_acceleration",  # D-44
    "receiver_park_factor_3yr",            # D-45
)

# Full feature set including all 4 new candidates
ALL_FEATURES_V2: tuple[str, ...] = ALL_FEATURES + NEW_FEATURES


def _fit_and_extract(
    train: pd.DataFrame,
    test: pd.DataFrame,
    outcome: str,
    feature_cols: tuple[str, ...],
    seed: int = 137,
) -> dict[str, float]:
    """Fit V3 model and return posterior mass and CI for each feature.

    Returns dict: feature_name → {mass, p05, p95} for features in feature_cols.
    Only reports the NEW_FEATURES — existing features omitted for brevity.
    """
    y = train[outcome].to_numpy(float)
    y_mean, y_std = float(y.mean()), float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    means = train[list(feature_cols)].mean()
    stds = train[list(feature_cols)].std().replace(0, 1.0)
    clip_lo = means - 5.0 * stds
    clip_hi = means + 5.0 * stds

    x = (
        train[list(feature_cols)]
        .clip(lower=clip_lo, upper=clip_hi, axis=1)
        .sub(means)
        .div(stds)
        .to_numpy(float)
    )

    with pm.Model():
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        beta = pm.Normal("beta", mu=0.0, sigma=0.3, shape=len(feature_cols))
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        mu = alpha0 + pm.math.dot(x, beta)
        pm.Normal("y_obs", mu=mu, sigma=sigma, observed=y_z)
        trace = pm.sample(
            1000, tune=1500, chains=4, random_seed=seed,
            progressbar=False, target_accept=0.95,
        )

    post_beta = trace.posterior["beta"].values  # (chains, draws, n_features)
    n_s = post_beta.shape[0] * post_beta.shape[1]
    post_flat = post_beta.reshape(n_s, len(feature_cols))

    results = {}
    for i, col in enumerate(feature_cols):
        if col not in NEW_FEATURES:
            continue
        samples = post_flat[:, i]
        p05 = float(np.percentile(samples, 5))
        p95 = float(np.percentile(samples, 95))
        mass_pos = float((samples > 0).mean())
        mass = max(mass_pos, 1.0 - mass_pos)
        results[col] = {"mass": mass, "p05": p05, "p95": p95, "mean": float(samples.mean())}

    return results


def run_cv(outcome: str, combined: pd.DataFrame) -> list[dict]:
    """Walk-forward CV for all 4 new features on one outcome."""
    feature_cols = ALL_FEATURES_V2
    min_n = MIN_TEST_N.get(outcome, 50)
    splits = walk_forward_splits(outcome, combined)
    rows = []

    for split in splits:
        logger.info("  %s  %s", outcome, split.label)
        t0 = time.time()
        train, test = _split_and_impute(
            outcome, feature_cols, split.train_end, split.test_end,
            combined=combined, train_start_season=split.train_start,
            minimum_features_present=1,
        )
        n_test = len(test)
        sufficient = n_test >= min_n

        feat_results: dict[str, dict] = {}
        if len(train) >= 50:
            feat_results = _fit_and_extract(train, test, outcome, feature_cols)

        row: dict = {
            "outcome": outcome,
            "fold": split.label,
            "train_end": split.train_end,
            "test_end": split.test_end,
            "n_train": len(train),
            "n_test": n_test,
            "sufficient": sufficient,
            "elapsed": round(time.time() - t0, 1),
        }
        for feat in NEW_FEATURES:
            fr = feat_results.get(feat, {})
            row[f"{feat}_mass"] = fr.get("mass", float("nan"))
            row[f"{feat}_mean"] = fr.get("mean", float("nan"))
            row[f"{feat}_p05"] = fr.get("p05", float("nan"))
            row[f"{feat}_p95"] = fr.get("p95", float("nan"))
            row[f"{feat}_credible"] = (
                fr.get("mass", 0) >= CV_MASS_THRESHOLD
                and (fr.get("p05", 0) > 0 or fr.get("p95", 0) < 0)
            ) if fr else False

        logger.info(
            "    ytd=%.0f%%  devfit_x_age=%.0f%%  accel=%.0f%%  park=%.0f%%  (%.1fs)",
            feat_results.get("receiver_acquired_origin_ytd_war", {}).get("mass", float("nan")) * 100,
            feat_results.get("receiver_devfit_x_peak_age", {}).get("mass", float("nan")) * 100,
            feat_results.get("receiver_acquired_war_acceleration", {}).get("mass", float("nan")) * 100,
            feat_results.get("receiver_park_factor_3yr", {}).get("mass", float("nan")) * 100,
            time.time() - t0,
        )
        rows.append(row)

    return rows


def print_report(all_rows: list[dict]) -> None:
    df = pd.DataFrame(all_rows)
    sep = "=" * 110

    feat_labels = {
        "receiver_acquired_origin_ytd_war": "origin_ytd_war (D-42)",
        "receiver_devfit_x_peak_age":        "devfit_x_age   (D-43)",
        "receiver_acquired_war_acceleration": "war_accel      (D-44)",
        "receiver_park_factor_3yr":           "park_factor    (D-45)",
    }

    print()
    print(sep)
    print("R-61–R-64: NEW FEATURE WALK-FORWARD CV RESULTS")
    print(f"Threshold: mass ≥ {CV_MASS_THRESHOLD:.0%} + 90% CI excludes zero → credible in fold")
    print(f"Confirmed: credible ≥ 3/4 sufficient folds with consistent sign")
    print(sep)

    for outcome in df["outcome"].unique():
        sub = df[df["outcome"] == outcome]
        suf = sub[sub["sufficient"]]
        print(f"\n  {outcome}  ({len(suf)} sufficient folds)")
        print(f"  {'fold':<20} {'n_test':>7}  ", end="")
        for feat in NEW_FEATURES:
            print(f"{'mass%':>7} {'cred?':>6}  ", end="")
        print()
        print(f"  {'':20} {'':>7}  ", end="")
        for feat in NEW_FEATURES:
            label = feat_labels[feat].split()[0][:12]
            print(f"{label:>7} {'':>6}  ", end="")
        print()
        print("  " + "-" * 100)

        for _, r in sub.iterrows():
            suf_mark = "" if r["sufficient"] else " INSUF"
            print(f"  {r['fold']:<20} {r['n_test']:>7}  ", end="")
            for feat in NEW_FEATURES:
                mass = r[f"{feat}_mass"]
                cred = r[f"{feat}_credible"]
                m_str = f"{mass*100:.0f}%" if not np.isnan(mass) else "  n/a"
                c_str = "✓" if cred else "·"
                print(f"{m_str:>7} {c_str:>6}  ", end="")
            print(suf_mark)

        # Verdicts per feature
        print()
        for feat in NEW_FEATURES:
            cred_folds = suf[f"{feat}_credible"].sum() if not suf.empty else 0
            total_suf = len(suf)
            means = suf[f"{feat}_mean"].dropna()
            pos_folds = (means > 0).sum() if len(means) else 0
            mass_avg = suf[f"{feat}_mass"].mean() if not suf.empty else float("nan")

            if total_suf == 0:
                verdict = "NO SUFFICIENT FOLDS"
            elif cred_folds >= 3:
                sign_ok = (pos_folds == cred_folds or pos_folds == 0)
                verdict = "CONFIRMED" if sign_ok else "EXPLORATORY (sign flip)"
            elif cred_folds >= 1:
                verdict = f"EXPLORATORY ({cred_folds}/{total_suf} folds)"
            else:
                verdict = f"NULL (0/{total_suf} folds credible)"

            print(f"  {feat_labels[feat]}: {verdict}  (avg mass={mass_avg:.0%})")

    print()
    print(sep)


def main() -> None:
    logger.info("Loading combined dataset (2010-2024) with new features...")
    combined = assemble_v3_combined()
    logger.info("combined: %d rows, checking new feature coverage...", len(combined))
    for feat in NEW_FEATURES:
        if feat in combined.columns:
            pct = combined[feat].notna().mean() * 100
            logger.info("  %s: %.0f%% non-null", feat, pct)
        else:
            logger.warning("  %s: MISSING from combined", feat)

    all_rows: list[dict] = []
    for outcome in ["war_delta", "dollar_surplus"]:
        rows = run_cv(outcome, combined)
        all_rows.extend(rows)

    print_report(all_rows)


if __name__ == "__main__":
    main()
