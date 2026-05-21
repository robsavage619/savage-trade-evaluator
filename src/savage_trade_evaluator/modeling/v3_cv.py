"""Walk-forward cross-validation for V3 Bayesian outcome models.

Addresses three methodological problems with single-split evaluation:
  1. Test-set contamination — 56 ablation rounds all evaluated on the same
     2021-2024 holdout inflates apparent credibility via researcher degrees of freedom.
  2. No multiple-comparisons control — features selected because they looked good on
     one specific test window.
  3. kpct_delta n_test=77 is too small for reliable per-feature inference.

Standard applied here:
  - Expanding-window walk-forward CV with 2-year test folds.
  - A feature is CONFIRMED only if it clears D-26 (90% CI excludes zero AND
    directional mass ≥ 97.5% — stricter than the ablation-phase 95%) in ≥ K/N folds
    AND the sign is consistent across all credible folds.
  - Folds with n_test < MIN_TEST_N are computed but marked INSUFFICIENT and do not
    count toward confirmation.
  - Results include per-fold CRPS distribution (mean ± std) to surface instability.

Credibility thresholds (conservative relative to ablation phase):
  - Single-fold: mass ≥ 97.5% (up from 95%) + CI excludes zero
  - Confirmation: credible in ≥ 3/4 folds for war_delta; ≥ 2/3 for kpct/xwoba
  - Sign consistency: direction must be the same in every credible fold

Minimum sample sizes:
  - war_delta:    n_test ≥ 100 per fold (2+ years of trades, well-powered)
  - kpct_delta:   n_test ≥ 30 per fold  (small population; flag as exploratory if any fold below 50)
  - xwoba_delta:  n_test ≥ 50 per fold
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v3 import (
    V3BacktestResult,
    backtest_outcome_v3,
    coefficient_summary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Outcome-level configuration
# ---------------------------------------------------------------------------

MIN_TEST_N: dict[str, int] = {
    "war_delta": 100,
    "kpct_delta": 30,
    "xwoba_delta": 50,
    "dollar_surplus": 100,
}

# Minimum fraction of folds a feature must be credible in to be CONFIRMED.
MIN_FOLD_FRACTION: dict[str, float] = {
    "war_delta": 0.75,    # ≥ 3/4
    "kpct_delta": 0.67,   # ≥ 2/3
    "xwoba_delta": 0.67,  # ≥ 2/3
    "dollar_surplus": 0.75,
}

# Directional mass threshold for single-fold credibility (stricter than ablation 95%).
CV_MASS_THRESHOLD: float = 0.975

# Test window size in seasons.
DEFAULT_TEST_WINDOW: int = 2


# ---------------------------------------------------------------------------
# Split definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CVSplit:
    """One walk-forward fold."""

    fold_idx: int
    train_start: int
    train_end: int    # inclusive
    test_start: int
    test_end: int     # inclusive

    @property
    def label(self) -> str:
        return f"fold{self.fold_idx}: train {self.train_start}–{self.train_end} → test {self.test_start}–{self.test_end}"


@dataclass
class CVFoldResult:
    """Results for one fold."""

    split: CVSplit
    n_train: int
    n_test: int
    crps: float
    coverage_90: float
    sufficient: bool           # n_test ≥ MIN_TEST_N
    feature_rows: pd.DataFrame  # from coefficient_summary


@dataclass
class V3CVResult:
    """Aggregated walk-forward CV result for one outcome + feature set."""

    outcome: str
    feature_cols: tuple[str, ...]
    splits: list[CVSplit]
    fold_results: list[CVFoldResult]
    feature_stability: pd.DataFrame   # per-feature cross-fold summary
    confirmed_features: pd.DataFrame  # features that clear the confirmation bar
    mean_crps: float
    std_crps: float
    exploratory_flag: bool             # True if any sufficient fold has n_test < 50


def walk_forward_splits(
    outcome: str,
    combined: pd.DataFrame,
    test_window: int = DEFAULT_TEST_WINDOW,
) -> list[CVSplit]:
    """Generate expanding-window walk-forward splits for one outcome.

    Uses seasons where the outcome is non-null. Minimum training set is
    5 seasons. Splits step forward by ``test_window`` seasons at a time,
    leaving at least one 2-year test window at the end.

    Args:
        outcome: Outcome column name (e.g. "war_delta").
        combined: Full combined DataFrame from assemble_v3_combined().
        test_window: Number of seasons per test fold.

    Returns:
        List of CVSplit objects in chronological order.
    """
    seasons = sorted(
        combined.loc[combined[outcome].notna(), "trade_season"].unique()
    )
    if len(seasons) < 7:
        logger.warning(
            "outcome %s has only %d seasons — walk-forward CV may be unreliable",
            outcome, len(seasons),
        )

    splits: list[CVSplit] = []
    min_train = 5   # minimum seasons in training set
    fold_idx = 1

    for test_start_idx in range(min_train, len(seasons) - test_window + 1, test_window):
        test_seasons = seasons[test_start_idx : test_start_idx + test_window]
        train_seasons = seasons[:test_start_idx]

        splits.append(CVSplit(
            fold_idx=fold_idx,
            train_start=int(train_seasons[0]),
            train_end=int(train_seasons[-1]),
            test_start=int(test_seasons[0]),
            test_end=int(test_seasons[-1]),
        ))
        fold_idx += 1

    return splits


def _fold_credible(
    feature_rows: pd.DataFrame,
    feature: str,
    mass_threshold: float = CV_MASS_THRESHOLD,
) -> tuple[bool, float, float]:
    """Return (is_credible, mean_beta, directional_mass) for a feature in one fold."""
    row = feature_rows[feature_rows["feature"] == feature]
    if row.empty:
        return False, float("nan"), float("nan")
    r = row.iloc[0]
    mean_beta = float(r["mean_beta"])
    mass = float(r["directional_mass"])
    p05 = float(r["p05"])
    p95 = float(r["p95"])
    ci_excludes_zero = (p05 > 0) or (p95 < 0)
    credible = ci_excludes_zero and (mass >= mass_threshold)
    return credible, mean_beta, mass


def _build_feature_stability(
    outcome: str,
    feature_cols: tuple[str, ...],
    fold_results: list[CVFoldResult],
    min_fold_fraction: float,
    mass_threshold: float = CV_MASS_THRESHOLD,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build per-feature stability table and confirmed-features subset.

    A feature is CONFIRMED if:
      1. Credible in ≥ ceil(min_fold_fraction × n_sufficient_folds) sufficient folds.
      2. Sign is consistent (all credible folds have the same beta sign).

    Returns:
        (feature_stability, confirmed_features) DataFrames.
    """
    sufficient_folds = [fr for fr in fold_results if fr.sufficient]
    n_sufficient = len(sufficient_folds)

    rows: list[dict] = []
    for feat in feature_cols:
        betas: list[float] = []
        masses: list[float] = []
        credible_count = 0
        insufficient_count = 0

        for fr in fold_results:
            credible, beta, mass = _fold_credible(fr.feature_rows, feat, mass_threshold)
            if not fr.sufficient:
                insufficient_count += 1
                continue
            betas.append(beta)
            masses.append(mass)
            if credible:
                credible_count += 1

        n_credible_needed = max(1, int(np.ceil(min_fold_fraction * n_sufficient)))
        consistent_sign = (
            len(betas) > 0
            and (all(b > 0 for b in betas if not np.isnan(b))
                 or all(b < 0 for b in betas if not np.isnan(b)))
        )
        confirmed = (
            n_sufficient > 0
            and credible_count >= n_credible_needed
            and consistent_sign
        )

        rows.append({
            "feature": feat,
            "n_sufficient_folds": n_sufficient,
            "n_credible_folds": credible_count,
            "n_needed": n_credible_needed,
            "median_beta": float(np.nanmedian(betas)) if betas else float("nan"),
            "beta_min": float(np.nanmin(betas)) if betas else float("nan"),
            "beta_max": float(np.nanmax(betas)) if betas else float("nan"),
            "median_mass": float(np.nanmedian(masses)) if masses else float("nan"),
            "consistent_sign": consistent_sign,
            "confirmed": confirmed,
            "n_insufficient_folds": insufficient_count,
        })

    stability = pd.DataFrame(rows)
    confirmed = stability[stability["confirmed"]].reset_index(drop=True)
    return stability, confirmed


def backtest_outcome_v3_cv(
    outcome: str,
    feature_cols: tuple[str, ...] | None = None,
    combined: pd.DataFrame | None = None,
    test_window: int = DEFAULT_TEST_WINDOW,
    mass_threshold: float = CV_MASS_THRESHOLD,
) -> V3CVResult:
    """Walk-forward cross-validated backtest for one outcome.

    Runs ``backtest_outcome_v3`` on each fold and aggregates results into a
    stability table. Features are confirmed only if credible in ≥ K/N
    sufficient folds with consistent sign.

    Args:
        outcome: Outcome variable name.
        feature_cols: Feature columns to use. Defaults to V3_OUTCOME_FEATURES[outcome].
        combined: Pre-loaded combined DataFrame (loaded internally if None).
        test_window: Seasons per test fold.
        mass_threshold: Minimum directional mass for single-fold credibility.

    Returns:
        V3CVResult with per-fold results, feature stability table, and confirmed features.
    """
    from savage_trade_evaluator.modeling.v3 import (
        V3_OUTCOME_FEATURES,
        assemble_v3_combined,
    )

    if combined is None:
        combined = assemble_v3_combined()
    if feature_cols is None:
        feature_cols = V3_OUTCOME_FEATURES[outcome]

    # Strip columns not present in combined (e.g., features not yet materialized).
    feature_cols = tuple(c for c in feature_cols if c in combined.columns)

    splits = walk_forward_splits(outcome, combined, test_window=test_window)
    if not splits:
        raise ValueError(f"no valid walk-forward splits for outcome '{outcome}'")

    min_n = MIN_TEST_N.get(outcome, 50)
    min_frac = MIN_FOLD_FRACTION.get(outcome, 0.75)

    fold_results: list[CVFoldResult] = []
    crps_values: list[float] = []

    for split in splits:
        logger.info("  %s", split.label)
        result: V3BacktestResult = backtest_outcome_v3(
            outcome,
            feature_cols=feature_cols,
            combined=combined,
            train_end_season=split.train_end,
            test_end_season=split.test_end,
            train_start_season=split.train_start,
        )
        coef_df = coefficient_summary(result.fit)
        sufficient = result.test_n >= min_n
        fold_results.append(CVFoldResult(
            split=split,
            n_train=result.train_n,
            n_test=result.test_n,
            crps=result.test_crps,
            coverage_90=result.coverage_90,
            sufficient=sufficient,
            feature_rows=coef_df,
        ))
        crps_values.append(result.test_crps)

        status = "OK" if sufficient else f"INSUFFICIENT (n_test={result.test_n} < {min_n})"
        logger.info(
            "    CRPS=%.4f  coverage=%.1f%%  n_train=%d  n_test=%d  %s",
            result.test_crps, result.coverage_90 * 100,
            result.train_n, result.test_n, status,
        )

    stability, confirmed = _build_feature_stability(
        outcome, feature_cols, fold_results, min_frac, mass_threshold
    )

    exploratory = any(
        fr.n_test < 50 for fr in fold_results if fr.sufficient
    )

    return V3CVResult(
        outcome=outcome,
        feature_cols=feature_cols,
        splits=splits,
        fold_results=fold_results,
        feature_stability=stability,
        confirmed_features=confirmed,
        mean_crps=float(np.mean(crps_values)),
        std_crps=float(np.std(crps_values)),
        exploratory_flag=exploratory,
    )


def print_cv_report(result: V3CVResult) -> None:
    """Print a formatted walk-forward CV report."""
    sep = "=" * 92
    print(sep)
    print(f"WALK-FORWARD CV: outcome={result.outcome}  ({len(result.feature_cols)} features)")
    if result.exploratory_flag:
        print("  *** EXPLORATORY — one or more folds has n_test < 50 ***")
    print(sep)
    print(f"  CRPS: {result.mean_crps:.4f} ± {result.std_crps:.4f}  across {len(result.fold_results)} folds")
    print()

    print(f"  {'Fold':<50} {'n_train':>7} {'n_test':>7} {'CRPS':>8} {'cov_90':>7}  status")
    print("  " + "-" * 86)
    for fr in result.fold_results:
        status = "ok" if fr.sufficient else "INSUF"
        print(
            f"  {fr.split.label:<50} {fr.n_train:>7} {fr.n_test:>7}"
            f" {fr.crps:>8.4f} {fr.coverage_90:>6.1%}  {status}"
        )

    print()
    print(f"  Feature stability  (mass threshold={CV_MASS_THRESHOLD:.1%}, min fraction={MIN_FOLD_FRACTION.get(result.outcome, 0.75):.0%})")
    print(f"  {'feature':<48} {'credible':>8} {'needed':>7} {'median_β':>9} {'range':>18}  {'sign':>5}  confirmed")
    print("  " + "-" * 110)

    for _, row in result.feature_stability.sort_values("n_credible_folds", ascending=False).iterrows():
        flag = "*** YES" if row["confirmed"] else "no"
        beta = f"{row['median_beta']:+.4f}" if not np.isnan(row["median_beta"]) else "   n/a"
        rng = (
            f"[{row['beta_min']:+.3f}, {row['beta_max']:+.3f}]"
            if not np.isnan(row["beta_min"]) else "     n/a     "
        )
        sign_ok = "✓" if row["consistent_sign"] else "✗"
        print(
            f"  {row['feature']:<48} {row['n_credible_folds']:>3}/{row['n_sufficient_folds']:<3}"
            f" {row['n_needed']:>7}  {beta:>9} {rng:>18}  {sign_ok:>5}  {flag}"
        )

    print()
    if not result.confirmed_features.empty:
        print(f"  CONFIRMED features ({len(result.confirmed_features)}):")
        for _, row in result.confirmed_features.iterrows():
            print(f"    *** {row['feature']}  median_β={row['median_beta']:+.4f}")
    else:
        print("  CONFIRMED features: none cleared the walk-forward bar")
    print(sep)
