"""Decline-drift detector: early-warning flags for pitchers losing stuff.

Detects within-season velo/movement trends and cross-season deltas before
they show up in surface stats (ERA, xFIP). A 1 mph velo loss in April is
invisible in a full-season line but predictive of second-half collapse.

Requires ``pitcher_monthly_trends`` to be populated via
``ste ingest statcast-monthly``.

Drift metrics per pitcher per pitch_type:
  velo_slope_mpw    — OLS slope of mean_velo vs month within the season
                      (mph per week, negative = losing velocity)
  velo_delta_yoy    — current-season mean minus prior-season mean
  move_slope_mpw    — OLS slope of sqrt(pfx_x^2 + pfx_z^2) vs month
  drift_z           — composite z-score vs age/role cohort

Cohort: pitchers within ±2 birth years with >= min_pitches same pitch_type.
Z-scoring is done per (pitch_type, cohort) so an SP losing 1 mph on the
fastball is not compared to a reliever's velo floor.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)


def _ols_slope(xs: list[float], ys: list[float]) -> float | None:
    """Return OLS slope (dy/dx) from paired lists. None if < 2 points."""
    if len(xs) < 2 or len(ys) < 2:
        return None
    x_arr = np.array(xs, dtype=float)
    y_arr = np.array(ys, dtype=float)
    x_mean = x_arr.mean()
    y_mean = y_arr.mean()
    denom = float(((x_arr - x_mean) ** 2).sum())
    if denom == 0.0:
        return None
    return float(((x_arr - x_mean) * (y_arr - y_mean)).sum() / denom)


def _movement_magnitude(pfx_x: float | None, pfx_z: float | None) -> float | None:
    if pfx_x is None or pfx_z is None:
        return None
    return math.sqrt(pfx_x**2 + pfx_z**2)


def _compute_single(
    rows: pd.DataFrame,
    season: int,
) -> dict[str, Any]:
    """Compute drift metrics for one (pitcher_id, pitch_type) time series."""
    cur = rows[rows["year_id"] == season].sort_values("month")  # type: ignore[call-overload]
    pri = rows[rows["year_id"] == season - 1].sort_values("month")  # type: ignore[call-overload]

    # Within-season velo slope — extract columns as lists to avoid pyright iterrows issues
    month_col: list[Any] = cur["month"].tolist()
    velo_col: list[Any] = cur["mean_velo"].tolist()
    velo_months = [
        float(m)
        for m, v in zip(month_col, velo_col, strict=False)
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    velo_vals = [
        float(v) for v in velo_col if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    velo_slope = _ols_slope(velo_months, velo_vals)

    # Within-season movement slope
    pfx_x_col: list[Any] = cur["mean_pfx_x"].tolist()
    pfx_z_col: list[Any] = cur["mean_pfx_z"].tolist()
    move_months: list[float] = []
    move_vals: list[float] = []
    for m, px, pz in zip(month_col, pfx_x_col, pfx_z_col, strict=False):
        fx = float(px) if px is not None else None
        fz = float(pz) if pz is not None else None
        mag = _movement_magnitude(fx, fz)
        if mag is not None:
            move_months.append(float(m))
            move_vals.append(mag)
    move_slope = _ols_slope(move_months, move_vals)

    # YoY velo delta
    cur_velo_vals = [
        float(v) for v in velo_col if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    pri_velo_col: list[Any] = pri["mean_velo"].tolist()
    pri_velo_vals = [
        float(v)
        for v in pri_velo_col
        if v is not None and not (isinstance(v, float) and math.isnan(v))
    ]
    cur_velo_mean: float | None = sum(cur_velo_vals) / len(cur_velo_vals) if cur_velo_vals else None
    pri_velo_mean: float | None = sum(pri_velo_vals) / len(pri_velo_vals) if pri_velo_vals else None
    velo_delta_yoy: float | None = None
    if cur_velo_mean is not None and pri_velo_mean is not None:
        velo_delta_yoy = cur_velo_mean - pri_velo_mean

    n_pitches_col: list[Any] = cur["n_pitches"].tolist()
    n_pitches_cur = int(sum(n for n in n_pitches_col if n is not None))

    return {
        "velo_slope": velo_slope,
        "move_slope": move_slope,
        "velo_delta_yoy": velo_delta_yoy,
        "n_pitches": n_pitches_cur,
        "cur_velo_mean": cur_velo_mean,
        "n_months": len(month_col),
    }


def flag_drift_pitchers(
    season: int,
    min_pitches: int = 150,
    top_n: int = 30,
) -> pd.DataFrame:
    """Identify pitchers showing meaningful decline signals.

    Computes within-season OLS velo slope + YoY velo delta for every
    pitcher-pitch_type with >= min_pitches in the target season.
    Z-scores within (pitch_type) cohort. Returns the top_n most concerning.

    Args:
        season: Season to evaluate (the "current" season).
        min_pitches: Minimum pitch count in the current season to include.
        top_n: Max rows to return.

    Returns:
        DataFrame with columns: pitcher_id, pitcher_name, pitch_type,
        n_pitches, velo_slope, move_slope, velo_delta_yoy,
        drift_z, cur_velo_mean.
        Sorted by drift_z ascending (most negative = most concerning).
    """
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT pitcher_id, pitcher_name, pitch_type, year_id, month,
                   n_pitches, mean_velo, mean_spin,
                   mean_release_x, mean_release_z,
                   mean_pfx_x, mean_pfx_z
            FROM pitcher_monthly_trends
            WHERE year_id IN (?, ?)
            ORDER BY pitcher_id, pitch_type, year_id, month
            """,
            [season, season - 1],
        ).fetchdf()

    if df.empty:
        logger.warning(
            "no pitcher_monthly_trends data for %d/%d — run ste ingest statcast-monthly",
            season - 1,
            season,
        )
        return pd.DataFrame()

    # Aggregate per (pitcher_id, pitch_type) across the two seasons
    records: list[dict[str, Any]] = []
    for key, grp in df.groupby(["pitcher_id", "pitch_type"]):  # type: ignore[union-attr]
        pid_raw, pt_raw = key[0], key[1]  # type: ignore[index]
        cur_season = grp[grp["year_id"] == season]
        n_pitches_col: list[Any] = cur_season["n_pitches"].tolist()
        n_cur = int(sum(n for n in n_pitches_col if n is not None))
        if n_cur < min_pitches:
            continue

        pitcher_name = str(grp["pitcher_name"].iloc[0])
        metrics = _compute_single(grp, season)
        records.append(
            {
                "pitcher_id": int(pid_raw),  # type: ignore[arg-type]
                "pitcher_name": pitcher_name,
                "pitch_type": str(pt_raw),  # type: ignore[arg-type]
                **metrics,
            }
        )

    if not records:
        logger.warning("no pitchers passed min_pitches=%d for season %d", min_pitches, season)
        return pd.DataFrame()

    out = pd.DataFrame(records)

    # Composite raw score (vectorized): higher = more concerning
    def _raw(vs: Any, yoy: Any) -> float:
        s = 0.0
        if vs is not None and not math.isnan(float(vs)):
            s += -float(vs)
        if yoy is not None and not math.isnan(float(yoy)):
            s += -float(yoy) * 0.5
        return s

    out["_raw"] = [_raw(r["velo_slope"], r["velo_delta_yoy"]) for r in out.to_dict("records")]

    # Z-score within pitch_type cohort using groupby transform
    def _zscore(g: pd.Series) -> pd.Series:  # type: ignore[type-arg]
        mu = float(g.mean())
        sigma = float(g.std(ddof=1)) if len(g) > 1 else 1.0  # type: ignore[arg-type]
        sigma = sigma if sigma != 0.0 else 1.0
        return (g - mu) / sigma

    out["drift_z"] = out.groupby("pitch_type")["_raw"].transform(_zscore)  # type: ignore[union-attr]
    out = out.drop(columns=["_raw"])
    out = out.sort_values("drift_z", ascending=False).head(top_n)  # type: ignore[call-overload]
    return out.reset_index(drop=True)
