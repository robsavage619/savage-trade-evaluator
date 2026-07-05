"""Score historical and hypothetical trade scenarios with posterior uncertainty.

Wraps the production fit cache (``production_fit.py``) and ``predict()`` to
produce JSON-serialisable posterior summaries for use in the War Room export.

Primary entry points:

* ``score_historical_scenarios(season, team_bref)`` — scores actual trades
  already in the DuckDB (trade_season = season). Useful for the War Room
  "scenarios" slot showing how the model rates trades that already happened.

* ``summarise_posterior(samples)`` — converts a 1-D numpy sample array
  to a JSON-ready dict with mean, median, HDI, p_positive, etc.

All posterior samples returned by ``predict()`` are in original outcome units
(WAR, dollars, wins) — no additional scaling is needed.
"""

from __future__ import annotations

import logging
from typing import Any, cast

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.production_fit import (
    TRAIN_END_SEASON,
    get_fit,
)
from savage_trade_evaluator.modeling.v3 import (
    V3FitResult,
    assemble_v3_combined,
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


def _score_df(
    df: pd.DataFrame,
    outcome: str,
    fit: V3FitResult,
) -> list[dict[str, Any]]:
    """Posterior-predictive summaries for each row of ``df``.

    Missing features in ``df`` are filled with the training-set column means
    stored in ``fit.feature_means``.

    Args:
        df: Feature DataFrame — must have at least the columns in ``fit.feature_cols``.
        outcome: Outcome name (used only for labelling).
        fit: Production ``V3FitResult`` from ``get_fit()``.

    Returns:
        List of posterior-summary dicts, one per row.
    """
    feat_cols = list(fit.feature_cols)
    scored_df = pd.DataFrame(index=df.index)
    for c in feat_cols:
        if c in df.columns:
            scored_df[c] = df[c].astype("float64")
        else:
            scored_df[c] = float(cast("float", fit.feature_means.get(c, 0.0)))
        scored_df[c] = scored_df[c].fillna(float(cast("float", fit.feature_means.get(c, 0.0))))

    samples_matrix = predict(fit, scored_df)  # (n_rows, n_samples)
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
        scenario: dict[str, Any] = {
            "trade_event_id": int(cast("int", row["trade_event_id"])),
            "trade_season": int(cast("int", row["trade_season"])),
            "receiver_bref": str(row["receiver_bref"]),
            "model_version": "v3.2",
            "train_end_season": TRAIN_END_SEASON,
        }
        for outcome in outcomes:
            scenario[outcome] = per_outcome[outcome][row_idx]
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
        Dict with metadata + per-outcome posterior summaries.
    """
    if len(features) != 1:
        raise ValueError(f"features must be a 1-row DataFrame; got {len(features)} rows")

    fits = {o: get_fit(o) for o in outcomes}
    result: dict[str, Any] = {
        "receiver_bref": receiver_bref,
        "sender_bref": sender_bref,
        "trade_season": trade_season,
        "model_version": "v3.2",
        "train_end_season": TRAIN_END_SEASON,
        "is_hypothetical": True,
    }
    for outcome in outcomes:
        summaries = _score_df(features, outcome, fits[outcome])
        result[outcome] = summaries[0]

    logger.info(
        "scored hypothetical trade: %s ← %s  war_delta_mean=%.2f",
        receiver_bref or "?",
        sender_bref or "?",
        result.get("war_delta", {}).get("mean", float("nan")),
    )
    return result
