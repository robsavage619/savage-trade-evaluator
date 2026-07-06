"""Score historical and hypothetical trade scenarios with posterior uncertainty.

Wraps the production fit cache (``production_fit.py``) and ``predict()`` to
produce JSON-serialisable posterior summaries for use in the War Room export.

Primary entry points:

* ``score_historical_scenarios(season, team_bref)`` — scores actual trades
  already in the DuckDB (trade_season = season). Useful for the War Room
  "scenarios" slot showing how the model rates trades that already happened.

* ``score_hypothetical(features, ...)`` — scores a pre-assembled feature row
  from ``feature_assembler.assemble_hypothetical()``.

* ``summarise_posterior(samples)`` — converts a 1-D numpy sample array
  to a JSON-ready dict with mean, median, HDI, p_positive, etc.

* ``coverage_report(features, fit)`` — data-coverage summary: fraction of
  features observed vs imputed, grade (A-D), list of imputed feature names.

* ``attribute_score(fit, features, top_k)`` — exact linear attribution of
  the model score: contribution_i = beta_mean_i x x_z_i x y_std.

All posterior samples returned by ``predict()`` are in original outcome units
(WAR, dollars, wins) — no additional scaling is needed.
"""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
from __future__ import annotations

import logging
from typing import Any, cast

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.production_fit import (
    MODEL_VERSION,
    TRAIN_END_SEASON,
    get_fit,
)
from savage_trade_evaluator.modeling.v3 import (
    V3FitResult,
    assemble_v3_combined,
    coefficient_summary,
    predict,
)

logger = logging.getLogger(__name__)

# Outcomes included in every scenario card.
SCENARIO_OUTCOMES = ("war_delta", "dollar_surplus", "surplus_wins")

# Minimum trade_season to surface in scenarios (skip data-sparse early era).
MIN_SCENARIO_SEASON = 2015


def summarise_posterior(samples: np.ndarray) -> dict[str, Any]:
    """Summarise a 1-D array of posterior-predictive samples.

    Args:
        samples: Posterior-predictive draws in original outcome units.

    Returns:
        Dict with keys: mean, median, sd, p5, p95, p_positive, n_samples.
    """
    p5, p95 = float(np.percentile(samples, 5)), float(np.percentile(samples, 95))
    return {
        "mean": float(np.mean(samples)),
        "median": float(np.median(samples)),
        "sd": float(np.std(samples)),
        "p5": p5,
        "p95": p95,
        "p_positive": float((samples > 0).mean()),
        "n_samples": len(samples),
    }


def _missing_mask(df: pd.DataFrame, fit: V3FitResult) -> np.ndarray:
    """Boolean array (n_rows, n_features) — True where value is NaN or column absent."""
    cols = list(fit.feature_cols)
    result = np.zeros((len(df), len(cols)), dtype=bool)
    for j, col in enumerate(cols):
        if col not in df.columns:
            result[:, j] = True
        else:
            result[:, j] = df[col].isna().to_numpy()
    return result


def coverage_report(features: pd.DataFrame, fit: V3FitResult) -> dict[str, Any]:
    """Data-coverage summary for a feature DataFrame against a production fit.

    Counts NaN cells (and absent columns) as imputed. For multi-row DataFrames
    a column is considered imputed if ANY row is missing.

    Args:
        features: Feature DataFrame (1+ rows).
        fit: Production V3FitResult defining the expected feature set.

    Returns:
        Dict with n_total, n_observed, n_imputed, observed_fraction, grade (A-D),
        and imputed_features (sorted list of column names).
    """
    mask = _missing_mask(features, fit)  # (n_rows, n_features)
    # Column-level: any missing row marks the column as imputed.
    missing_by_col = mask.any(axis=0) if len(features) > 1 else mask[0]

    n_total = len(fit.feature_cols)
    n_imputed = int(missing_by_col.sum())
    n_observed = n_total - n_imputed
    observed_fraction = n_observed / n_total if n_total > 0 else 0.0

    if observed_fraction >= 0.8:
        grade = "A"
    elif observed_fraction >= 0.6:
        grade = "B"
    elif observed_fraction >= 0.4:
        grade = "C"
    else:
        grade = "D"

    imputed_features = sorted(
        fit.feature_cols[j] for j, m in enumerate(missing_by_col.tolist()) if m
    )
    return {
        "n_total": n_total,
        "n_observed": n_observed,
        "n_imputed": n_imputed,
        "observed_fraction": round(observed_fraction, 4),
        "grade": grade,
        "imputed_features": imputed_features,
    }


def attribute_score(
    fit: V3FitResult,
    features: pd.DataFrame,
    top_k: int = 5,
) -> dict[str, Any]:
    """Exact per-feature attribution using posterior mean coefficients.

    contribution_i = beta_mean_i x x_z_i x y_std

    NaN features are zeroed in z-space (identical to mean imputation), so their
    contribution is 0 by construction. This stays true under marginal multiple
    imputation because imputation draws are zero-mean — the expected contribution
    of a missing feature is 0.

    Dollar_surplus units: the production fit trains on raw dollars (not
    signed-log), so attribution is in original outcome units for all three
    production outcomes.

    Args:
        fit: Production V3FitResult.
        features: 1-row feature DataFrame (from assemble_hypothetical).
        top_k: Number of top contributors by |contribution| to return.

    Returns:
        Dict with baseline, top_contributors (list of dicts), sum_all,
        reconstructed_mean.
    """
    cols = list(fit.feature_cols)

    # Standardize exactly as predict() does; NaN → 0 in z-space = zero contribution.
    df_clipped = features[cols].clip(lower=fit.feature_clip_lo, upper=fit.feature_clip_hi, axis=1)
    x_z = ((df_clipped - fit.feature_means) / fit.feature_stds).fillna(0.0).to_numpy(dtype=float)[0]

    post = fit.trace.posterior
    n_samples = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_mean = float(post["alpha0"].values.reshape(n_samples).mean())
    beta_mean = post["beta"].values.reshape(n_samples, len(cols)).mean(axis=0)

    # Baseline: alpha0 when all features are at training mean (z=0).
    baseline = alpha0_mean * fit.y_std + fit.y_mean

    # Per-feature contribution in original outcome units.
    contributions = beta_mean * x_z * fit.y_std

    # Credibility from the D-26 flag (CI excludes zero AND directional mass ≥ 0.95).
    coeff_df = coefficient_summary(fit)
    credible_map = dict(zip(coeff_df["feature"], coeff_df["credible"], strict=False))

    # Observed flags from pre-imputation NaN mask.
    missing_row = features[cols].isna().to_numpy()[0]

    items: list[dict[str, Any]] = [
        {
            "feature": col,
            "value_z": round(float(x_z[j]), 4),
            "contribution": round(float(contributions[j]), 6),
            "observed": not bool(missing_row[j]),
            "credible": bool(credible_map.get(col, False)),
        }
        for j, col in enumerate(cols)
    ]
    items.sort(key=lambda d: abs(d["contribution"]), reverse=True)

    sum_all = float(contributions.sum())
    return {
        "baseline": round(baseline, 6),
        "top_contributors": items[:top_k],
        "sum_all": round(sum_all, 6),
        "reconstructed_mean": round(baseline + sum_all, 6),
    }


def _score_df(
    df: pd.DataFrame,
    outcome: str,
    fit: V3FitResult,
) -> list[dict[str, Any]]:
    """Posterior-predictive summaries for each row of ``df``.

    Missing features are handled via multiple imputation inside ``predict()``
    (per-sample z-space draws, marginal), which widens posteriors for sparse
    rows relative to the old mean-fill approach.

    Args:
        df: Feature DataFrame — must have at least the columns in ``fit.feature_cols``.
        outcome: Outcome name (used only for labelling).
        fit: Production ``V3FitResult`` from ``get_fit()``.

    Returns:
        List of posterior-summary dicts, one per row.
    """
    feat_cols = list(fit.feature_cols)
    # Ensure all expected columns are present and float64; leave NaN as NaN
    # so predict() can identify and impute them per-sample.
    scored_df = pd.DataFrame(index=df.index)
    for c in feat_cols:
        if c in df.columns:
            scored_df[c] = df[c].astype("float64")
        else:
            scored_df[c] = float("nan")  # absent column = fully missing

    samples_matrix = predict(fit, scored_df, multiple_imputation=True)  # (n_rows, n_samples)
    return [summarise_posterior(samples_matrix[i]) for i in range(len(df))]


def score_historical_scenarios(
    season: int,
    team_bref: str | None = None,
    combined: pd.DataFrame | None = None,
    outcomes: tuple[str, ...] = SCENARIO_OUTCOMES,
) -> list[dict[str, Any]]:
    """Score actual trades from a given season using production model posteriors.

    Uses data from ``assemble_v3_combined()`` filtered to ``season``. Only
    trades with ``trade_season > TRAIN_END_SEASON`` are scored (the model
    was not trained on them, so these are genuine out-of-sample predictions).

    Args:
        season: Trade season to score (e.g. 2024).
        team_bref: If set, only return scenarios where the receiving team is
            this Baseball-Reference team code.
        combined: Pre-loaded combined DataFrame. Loaded internally if None.
        outcomes: Outcomes to include in each scenario card.

    Returns:
        List of scenario dicts, one per (trade_event_id, receiver_bref) row.
        Each dict contains trade metadata + posterior summaries per outcome.
        Each outcome summary includes a ``coverage`` sub-dict.
        war_delta also includes an ``attribution`` sub-dict.
    """
    if season <= TRAIN_END_SEASON:
        logger.warning(
            "season %d is in the training window (≤ %d); predictions will be in-sample",
            season,
            TRAIN_END_SEASON,
        )
    if season < MIN_SCENARIO_SEASON:
        raise ValueError(f"season {season} < MIN_SCENARIO_SEASON={MIN_SCENARIO_SEASON}")

    if combined is None:
        combined = assemble_v3_combined()

    mask = combined["trade_season"] == season
    if team_bref:
        mask = mask & (combined["receiver_bref"] == team_bref)
    subset = cast("pd.DataFrame", combined[mask]).copy()

    if subset.empty:
        logger.warning("no trades found for season=%d team_bref=%s", season, team_bref)
        return []

    logger.info(
        "scoring %d historical trade rows: season=%d team_bref=%s",
        len(subset),
        season,
        team_bref,
    )

    # Load all fits up front to avoid re-loading per row.
    fits = {o: get_fit(o) for o in outcomes}

    # Score all rows for each outcome in one batch call, then zip into scenario dicts.
    per_outcome: dict[str, list[dict[str, Any]]] = {}
    for outcome in outcomes:
        per_outcome[outcome] = _score_df(subset, outcome, fits[outcome])

    scenarios: list[dict[str, Any]] = []
    for row_idx, (_, row) in enumerate(subset.iterrows()):
        # Build a 1-row DataFrame for per-row coverage and attribution.
        row_df = cast("pd.DataFrame", subset.iloc[[row_idx]])

        scenario: dict[str, Any] = {
            "trade_event_id": int(cast("int", row["trade_event_id"])),
            "trade_season": int(cast("int", row["trade_season"])),
            "receiver_bref": str(row["receiver_bref"]),
            "model_version": MODEL_VERSION,
            "train_end_season": TRAIN_END_SEASON,
        }
        for outcome in outcomes:
            fit = fits[outcome]
            outcome_summary = dict(per_outcome[outcome][row_idx])
            outcome_summary["coverage"] = coverage_report(row_df, fit)
            # Attribution only for war_delta (keeps payload small for historical batch).
            if outcome == "war_delta":
                outcome_summary["attribution"] = attribute_score(fit, row_df, top_k=5)
            scenario[outcome] = outcome_summary
        scenarios.append(scenario)

    logger.info("scored %d scenarios for season=%d", len(scenarios), season)
    return scenarios


def score_hypothetical(
    features: pd.DataFrame,
    outcomes: tuple[str, ...] = SCENARIO_OUTCOMES,
    receiver_bref: str | None = None,
    sender_bref: str | None = None,
    trade_season: int | None = None,
) -> dict[str, Any]:
    """Score a hypothetical trade from a pre-assembled feature row.

    Designed to work with ``feature_assembler.assemble_hypothetical()``.
    The model used is the same production fit as ``score_historical_scenarios``,
    trained on data through ``TRAIN_END_SEASON``.

    Args:
        features: 1-row DataFrame from ``assemble_hypothetical()``.
        outcomes: Outcomes to score (default: war_delta, dollar_surplus, surplus_wins).
        receiver_bref: Optional receiving team label for the returned dict.
        sender_bref: Optional sending team label for the returned dict.
        trade_season: Optional trade season label for the returned dict.

    Returns:
        Dict with metadata + per-outcome posterior summaries. Each outcome summary
        includes a ``coverage`` sub-dict. All outcomes include ``attribution``.
        Top-level ``data_coverage`` mirrors war_delta's coverage (the primary outcome).
    """
    if len(features) != 1:
        raise ValueError(f"features must be a 1-row DataFrame; got {len(features)} rows")

    fits = {o: get_fit(o) for o in outcomes}
    result: dict[str, Any] = {
        "receiver_bref": receiver_bref,
        "sender_bref": sender_bref,
        "trade_season": trade_season,
        "model_version": MODEL_VERSION,
        "train_end_season": TRAIN_END_SEASON,
        "is_hypothetical": True,
    }
    for outcome in outcomes:
        fit = fits[outcome]
        summaries = _score_df(features, outcome, fit)
        outcome_summary = dict(summaries[0])
        outcome_summary["coverage"] = coverage_report(features, fit)
        outcome_summary["attribution"] = attribute_score(fit, features, top_k=5)
        result[outcome] = outcome_summary

    # Top-level convenience key: war_delta coverage (the primary outcome).
    war_fit = fits.get("war_delta")
    if war_fit is not None:
        result["data_coverage"] = coverage_report(features, war_fit)

    logger.info(
        "scored hypothetical trade: %s ← %s  war_delta_mean=%.2f  coverage=%s",
        receiver_bref or "?",
        sender_bref or "?",
        result.get("war_delta", {}).get("mean", float("nan")),
        result.get("data_coverage", {}).get("grade", "?"),
    )
    return result
