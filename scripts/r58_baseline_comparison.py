"""R-58: Baseline comparison — confirmed-feature model vs intercept-only.

Runs the same walk-forward CV folds as R-57 but computes CRPS for three models:
  1. Intercept-only: predict N(training_mean, training_std) for every test obs.
     This is the "predict the mean" floor — any useful model must beat this.
  2. Player-quality only: single feature (receiver_acquired_player_quality),
     which is the one feature confirmed across all 5 folds for war_delta /
     dollar_surplus. Tests whether additional confirmed features add value.
  3. Confirmed-feature model (R-57 results, re-run to verify).

CRPS for a normal prediction N(mu, sigma) evaluated at y has the analytic form:
  sigma * [z*(2*Phi(z) - 1) + 2*phi(z) - 1/sqrt(pi)]
where z = (y - mu) / sigma. We use this for the intercept-only baseline to
avoid MCMC overhead, and sample-based CRPS for the feature models.

Output: per-fold and aggregate comparison table for each outcome.
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
logger = logging.getLogger("r58")

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

from savage_trade_evaluator.modeling.v2.backtest import _crps_empirical
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


def _crps_normal(mu: float, sigma: float, y: np.ndarray) -> float:
    """Analytic CRPS for N(mu, sigma) predictions evaluated at y values.

    CRPS(N(μ,σ), y) = σ * [z*(2Φ(z)−1) + 2φ(z) − 1/√π]
    where z = (y − μ) / σ.
    Averaged across all y values.
    """
    z = (y - mu) / sigma
    phi = scipy_stats.norm.pdf(z)
    big_phi = scipy_stats.norm.cdf(z)
    per_obs = sigma * (z * (2 * big_phi - 1) + 2 * phi - 1 / np.sqrt(np.pi))
    return float(per_obs.mean())


def _fit_bayesian_intercept_only(
    train: pd.DataFrame,
    test: pd.DataFrame,
    outcome: str,
) -> float:
    """CRPS for a Bayesian intercept-only model (alpha + sigma, no features).

    Same prior structure as fit_v3 so the comparison is architecturally fair.
    This is the proper baseline: what does MCMC-estimated uncertainty look like
    when we have zero features? Any gain from the feature model above this
    baseline reflects the features' contribution to CRPS.
    """
    import pymc as pm  # local import to keep startup fast

    y = train[outcome].to_numpy(float)
    y_mean = float(y.mean())
    y_std = float(y.std()) or 1.0
    y_z = (y - y_mean) / y_std

    with pm.Model():
        alpha0 = pm.Normal("alpha0", mu=0.0, sigma=1.0)
        sigma = pm.HalfNormal("sigma", sigma=1.0)
        pm.Normal("y_obs", mu=alpha0, sigma=sigma, observed=y_z)
        trace = pm.sample(
            1500, tune=2000, chains=4, random_seed=137, progressbar=False, target_accept=0.99
        )

    post = trace.posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n_samples)
    sigma_s = post["sigma"].values.reshape(n_samples)

    y_test = test[outcome].to_numpy(float)
    n_test = len(y_test)
    preds = np.zeros((n_test, n_samples))
    rng = np.random.default_rng(seed=137)
    for i in range(n_test):
        mu_z = alpha0_s
        noise = rng.normal(0.0, sigma_s)
        preds[i] = (mu_z + noise) * y_std + y_mean

    return _crps_empirical(y_test, preds)


def run_fold_comparison(
    outcome: str,
    feature_cols: tuple[str, ...],
    combined: pd.DataFrame,
    train_end: int,
    test_end: int,
    train_start: int,
    min_n: int,
) -> dict:
    """One fold: Bayesian intercept-only + player-quality-only + confirmed-feature CRPS."""
    train, test = _split_and_impute(
        outcome,
        feature_cols,
        train_end,
        test_end,
        combined=combined,
        train_start_season=train_start,
    )
    n_train, n_test = len(train), len(test)
    sufficient = n_test >= min_n
    y_test = test[outcome].to_numpy(float)

    # --- analytic bound: N(train_mean, train_std) — best possible calibrated prediction ---
    mu_train = float(train[outcome].mean())
    sig_train = float(train[outcome].std()) or 1.0
    crps_analytic = _crps_normal(mu_train, sig_train, y_test)

    # --- baseline 1 (FAIR): Bayesian intercept-only, same prior structure as feature model ---
    crps_intercept = float("nan")
    if len(train) >= 50:
        crps_intercept = _fit_bayesian_intercept_only(train, test, outcome)

    # --- baseline 2: player-quality single feature (if available) ---
    crps_quality = float("nan")
    quality_col = "receiver_acquired_player_quality"
    if quality_col in feature_cols and quality_col in combined.columns:
        train_q, test_q = _split_and_impute(
            outcome,
            (quality_col,),
            train_end,
            test_end,
            combined=combined,
            train_start_season=train_start,
            minimum_features_present=1,
        )
        if len(train_q) >= 50:
            fit_q = fit_v3(train_q, outcome, (quality_col,))
            preds_q = predict(fit_q, test_q)
            y_test_q = test_q[outcome].to_numpy(float)
            crps_quality = _crps_empirical(y_test_q, preds_q)

    # --- model: confirmed-feature set ---
    crps_model = float("nan")
    if len(train) >= 50:
        fit_m = fit_v3(train, outcome, feature_cols)
        preds_m = predict(fit_m, test)
        crps_model = _crps_empirical(y_test, preds_m)

    return {
        "outcome": outcome,
        "train_end": train_end,
        "test_end": test_end,
        "n_train": n_train,
        "n_test": n_test,
        "sufficient": sufficient,
        "crps_analytic": crps_analytic,  # theoretical lower bound: N(mu, sigma) analytic
        "crps_intercept": crps_intercept,  # Bayesian intercept-only (fair comparison)
        "crps_quality": crps_quality,
        "crps_model": crps_model,
        "skill_vs_bayes_intercept": 1.0 - (crps_model / crps_intercept)
        if not np.isnan(crps_intercept) and crps_intercept
        else float("nan"),
        "skill_quality_vs_bayes_intercept": 1.0 - (crps_quality / crps_intercept)
        if not np.isnan(crps_intercept) and crps_intercept
        else float("nan"),
        "skill_model_vs_quality": 1.0 - (crps_model / crps_quality)
        if not np.isnan(crps_quality) and crps_quality
        else float("nan"),
    }


def print_comparison(rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    outcomes = df["outcome"].unique()

    sep = "=" * 108
    print()
    print(sep)
    print("R-58 BASELINE COMPARISON")
    print(
        "Columns: analytic=N(mu,sigma) theoretical bound | bayes_int=intercept-only MCMC | quality=single-feature | model=confirmed-feature set"
    )
    print("Skill score = 1 − (CRPS_model / CRPS_reference).  Positive = model beats reference.")
    print(sep)

    for outcome in outcomes:
        sub = df[df["outcome"] == outcome].copy()
        sufficient = sub[sub["sufficient"]]
        print()
        print(f"  {outcome}  ({len(sub)} folds, {len(sufficient)} sufficient)")
        print(
            f"  {'fold window':<15} {'n_test':>7} {'analytic':>10} {'bayes_int':>10} {'quality':>10} {'model':>10}  {'skill(mdl/int)':>14}  {'skill(mdl/qlty)':>15}"
        )
        print("  " + "-" * 96)
        for _, r in sub.iterrows():
            suf = "" if r["sufficient"] else " INSUF"
            bi = (
                f"{r['crps_intercept']:>10.4f}"
                if not np.isnan(r["crps_intercept"])
                else "       n/a"
            )
            qi = f"{r['crps_quality']:>10.4f}" if not np.isnan(r["crps_quality"]) else "       n/a"
            mi = f"{r['crps_model']:>10.4f}" if not np.isnan(r["crps_model"]) else "       n/a"
            sk = (
                f"{r['skill_vs_bayes_intercept']:>+13.1%}"
                if not np.isnan(r["skill_vs_bayes_intercept"])
                else "           n/a"
            )
            smq = (
                f"{r['skill_model_vs_quality']:>+14.1%}"
                if not np.isnan(r["skill_model_vs_quality"])
                else "            n/a"
            )
            print(
                f"  {r['test_end'] - 1}–{r['test_end']:<10} {r['n_test']:>7} {r['crps_analytic']:>10.4f} {bi} {qi} {mi}  {sk}  {smq}{suf}"
            )

        if not sufficient.empty:
            print()
            cols_to_agg = [
                "crps_analytic",
                "crps_intercept",
                "crps_quality",
                "crps_model",
                "skill_vs_bayes_intercept",
                "skill_model_vs_quality",
            ]
            agg = sufficient[cols_to_agg].mean()
            print(
                f"  Mean (sufficient):              "
                f"{agg['crps_analytic']:>10.4f} {agg['crps_intercept']:>10.4f} "
                f"{agg['crps_quality']:>10.4f} {agg['crps_model']:>10.4f}  "
                f"{agg['skill_vs_bayes_intercept']:>+13.1%}  {agg['skill_model_vs_quality']:>+14.1%}"
            )

    print()
    print(sep)
    print("  analytic < bayes_int  → Bayesian uncertainty adds overhead vs knowing sigma exactly")
    print("  skill(mdl/int) > 0    → feature model beats intercept-only Bayesian baseline")
    print("  skill(mdl/qlty) > 0   → extra features beyond quality add predictive value")
    print("  skill < 0             → the reference is better; model adds noise")
    print(sep)


def main() -> None:
    logger.info("Loading combined dataset...")
    combined = assemble_v3_combined()
    logger.info("combined: %d rows", len(combined))

    all_rows: list[dict] = []

    # war_delta and dollar_surplus: 5 folds, main validation outcomes.
    # surplus_wins: dollar_surplus / $/WAR — wins-denominated, Phase B.
    # xwoba/kpct: 1 fold only — exploratory, skip baseline comparison.
    outcomes = ["war_delta", "dollar_surplus", "surplus_wins"]

    for outcome in outcomes:
        feature_cols = V3_OUTCOME_FEATURES[outcome]
        min_n = MIN_TEST_N.get(outcome, 50)
        splits = walk_forward_splits(outcome, combined)
        logger.info("%s: %d folds, %d features", outcome, len(splits), len(feature_cols))

        for split in splits:
            logger.info("  %s", split.label)
            t0 = time.time()
            row = run_fold_comparison(
                outcome=outcome,
                feature_cols=feature_cols,
                combined=combined,
                train_end=split.train_end,
                test_end=split.test_end,
                train_start=split.train_start,
                min_n=min_n,
            )
            elapsed = time.time() - t0
            skill = row["skill_vs_bayes_intercept"]
            logger.info(
                "    analytic=%.4f  bayes_int=%.4f  quality=%.4f  model=%.4f  skill=%.1f%%  (%.1fs)",
                row["crps_analytic"],
                row["crps_intercept"],
                row["crps_quality"],
                row["crps_model"],
                (skill * 100) if not np.isnan(skill) else float("nan"),
                elapsed,
            )
            all_rows.append(row)

    print_comparison(all_rows)


if __name__ == "__main__":
    main()
