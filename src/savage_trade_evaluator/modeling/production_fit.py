"""Production model fits: train on full historical data and cache to disk.

The production fit trains on all available data up to TRAIN_END_SEASON (default
2022). It is cached to ``data/model_cache/`` as ArviZ NetCDF (trace) + JSON
sidecar (feature normalisation stats). Cache is invalidated when MODEL_VERSION
or SCHEMA_VERSION changes.

Usage::

    from savage_trade_evaluator.modeling.production_fit import get_fit
    fit = get_fit("war_delta")   # loads cache or retrains
    fit = get_fit("war_delta", force_retrain=True)  # always retrains

The cache directory is gitignored; regenerate locally after any schema bump.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import arviz as az
import numpy as np
import pandas as pd

from savage_trade_evaluator.config import DATA_DIR
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    V3FitResult,
    assemble_v3_combined,
    fit_v3,
)
from savage_trade_evaluator.storage.schemas import SCHEMA_VERSION

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Bump when model architecture or feature set changes — invalidates cached fits.
MODEL_VERSION = "v3.2"

# Train on data through this season; 2023-2024 trades are held for scenario scoring.
TRAIN_END_SEASON = 2022

CACHE_DIR = DATA_DIR / "model_cache"

OUTCOMES_DEFAULT = ("war_delta", "dollar_surplus", "surplus_wins")


def _trace_path(outcome: str) -> Path:
    return CACHE_DIR / f"{outcome}_v{MODEL_VERSION}_schema{SCHEMA_VERSION}.nc"


def _meta_path(outcome: str) -> Path:
    return CACHE_DIR / f"{outcome}_v{MODEL_VERSION}_schema{SCHEMA_VERSION}.json"


def _cache_valid(outcome: str) -> bool:
    """True if both cache files exist and the meta version tags match."""
    nc = _trace_path(outcome)
    meta = _meta_path(outcome)
    if not nc.exists() or not meta.exists():
        return False
    try:
        with meta.open() as f:
            m = json.load(f)
        return m.get("model_version") == MODEL_VERSION and m.get("schema_version") == SCHEMA_VERSION
    except (json.JSONDecodeError, OSError):
        return False


def _save(fit: V3FitResult, outcome: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fit.trace.to_netcdf(_trace_path(outcome))  # type: ignore[attr-defined]
    meta = {
        "model_version": MODEL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "train_end_season": TRAIN_END_SEASON,
        "outcome": outcome,
        "feature_cols": list(fit.feature_cols),
        "feature_means": fit.feature_means.to_dict(),
        "feature_stds": fit.feature_stds.to_dict(),
        "feature_clip_lo": fit.feature_clip_lo.to_dict(),
        "feature_clip_hi": fit.feature_clip_hi.to_dict(),
        "y_mean": fit.y_mean,
        "y_std": fit.y_std,
    }
    with _meta_path(outcome).open("w") as f:
        json.dump(meta, f, indent=2)
    logger.info("cached production fit: %s → %s", outcome, _trace_path(outcome))


def _load(outcome: str) -> V3FitResult:
    with _meta_path(outcome).open() as f:
        m = json.load(f)
    trace = az.from_netcdf(_trace_path(outcome))
    feature_cols = tuple(m["feature_cols"])
    idx = pd.Index(feature_cols)
    return V3FitResult(
        trace=trace,
        feature_cols=feature_cols,
        feature_means=pd.Series(m["feature_means"], index=idx),
        feature_stds=pd.Series(m["feature_stds"], index=idx),
        feature_clip_lo=pd.Series(m["feature_clip_lo"], index=idx),
        feature_clip_hi=pd.Series(m["feature_clip_hi"], index=idx),
        y_mean=float(m["y_mean"]),
        y_std=float(m["y_std"]),
    )


def _train_and_cache(outcome: str, combined: pd.DataFrame | None = None) -> V3FitResult:
    """Fit the model on data ≤ TRAIN_END_SEASON and cache the result."""
    if combined is None:
        combined = assemble_v3_combined()
    feature_cols = V3_OUTCOME_FEATURES[outcome]
    train = combined[
        combined[outcome].notna() & (combined["trade_season"] <= TRAIN_END_SEASON)
    ].copy()

    # Impute using training-set means only.
    for c in feature_cols:
        fill = float(train[c].astype("float64").mean())
        if np.isnan(fill):
            fill = 0.0
        train[c] = train[c].astype("float64").fillna(fill)

    logger.info("training production fit: outcome=%s  n=%d", outcome, len(train))
    fit = fit_v3(train, outcome, feature_cols)
    _save(fit, outcome)
    return fit


def get_fit(
    outcome: str,
    combined: pd.DataFrame | None = None,
    force_retrain: bool = False,
) -> V3FitResult:
    """Return the production fit for ``outcome``, training if the cache is stale.

    Args:
        outcome: Outcome variable name (e.g. ``"war_delta"``).
        combined: Pre-loaded combined DataFrame. Loaded internally if None.
        force_retrain: If True, retrain even when the cache is valid.

    Returns:
        ``V3FitResult`` trained on data through ``TRAIN_END_SEASON``.
    """
    if not force_retrain and _cache_valid(outcome):
        logger.info("loading cached production fit: %s", outcome)
        return _load(outcome)
    return _train_and_cache(outcome, combined)


def warm_cache(
    outcomes: tuple[str, ...] = OUTCOMES_DEFAULT,
    force_retrain: bool = False,
) -> None:
    """Pre-train and cache production fits for all default outcomes.

    Args:
        outcomes: Outcomes to cache.
        force_retrain: Retrain even when cached fits exist.
    """
    combined = assemble_v3_combined()
    for outcome in outcomes:
        get_fit(outcome, combined=combined, force_retrain=force_retrain)
    logger.info("production cache warm: %d outcomes", len(outcomes))
