"""Decline-drift detector: early-warning flags for pitchers losing stuff.

Sources from ``statcast_pitch_movement`` (already populated 2015-2026,
per-pitcher-per-pitch_type per season). Detects cross-season velo decay and
movement loss before surface stats (ERA, xFIP) react.

Drift metrics per pitcher per pitch_type:
  velo_delta_yoy    -- avg_speed[season] - avg_speed[season-1]
  hmove_delta_yoy   -- horizontal_break_inches delta (sign-preserving)
  vmove_delta_yoy   -- vertical_break_inches delta
  drift_z           -- composite z-score within pitch_type cohort
                       (negative = most concerning)
"""

from __future__ import annotations

import logging
import math
from typing import Any

import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)


def flag_drift_pitchers(
    season: int,
    min_pitches: int = 150,
    top_n: int = 30,
) -> pd.DataFrame:
    """Identify pitchers showing meaningful decline signals.

    Compares avg_speed and movement for each pitcher-pitch_type between
    ``season`` and ``season - 1``. Z-scores within pitch_type cohort.
    Returns top_n most concerning (most negative drift_z).

    Args:
        season: The "current" season to evaluate.
        min_pitches: Minimum pitches_thrown in the current season to include.
        top_n: Max rows to return.

    Returns:
        DataFrame with columns: player_id, player_name, pitch_type, n_pitches,
        avg_speed_cur, velo_delta_yoy, hmove_delta_yoy, vmove_delta_yoy, drift_z.
        Sorted by drift_z ascending (most negative = most concerning).
    """
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT player_id, player_name, pitch_type,
                   year, avg_speed, horizontal_break_inches,
                   vertical_break_inches, pitches_thrown
            FROM statcast_pitch_movement
            WHERE year IN (?, ?)
              AND pitches_thrown IS NOT NULL
            ORDER BY player_id, pitch_type, year
            """,
            [season, season - 1],
        ).fetchdf()

    if df.empty:
        logger.warning(
            "no statcast_pitch_movement data for %d/%d — run ste ingest statcast",
            season - 1,
            season,
        )
        return pd.DataFrame()

    records: list[dict[str, Any]] = []
    for (pid, pt), grp in df.groupby(["player_id", "pitch_type"]):  # type: ignore[union-attr]
        cur = grp[grp["year"] == season]
        pri = grp[grp["year"] == season - 1]
        if cur.empty:
            continue
        n_pitches = int(cur["pitches_thrown"].iloc[0] or 0)
        if n_pitches < min_pitches:
            continue
        if pri.empty:
            continue

        cur_speed = cur["avg_speed"].iloc[0]
        pri_speed = pri["avg_speed"].iloc[0]
        cur_hmove = cur["horizontal_break_inches"].iloc[0]
        pri_hmove = pri["horizontal_break_inches"].iloc[0]
        cur_vmove = cur["vertical_break_inches"].iloc[0]
        pri_vmove = pri["vertical_break_inches"].iloc[0]

        def _delta(a: Any, b: Any) -> float | None:
            if a is None or b is None:
                return None
            try:
                fa, fb = float(a), float(b)
            except (TypeError, ValueError):
                return None
            if math.isnan(fa) or math.isnan(fb):
                return None
            return fa - fb

        records.append(
            {
                "player_id": int(pid),  # type: ignore[arg-type]
                "player_name": str(cur["player_name"].iloc[0]),
                "pitch_type": str(pt),  # type: ignore[arg-type]
                "n_pitches": n_pitches,
                "avg_speed_cur": float(cur_speed) if cur_speed is not None else None,
                "velo_delta_yoy": _delta(cur_speed, pri_speed),
                "hmove_delta_yoy": _delta(cur_hmove, pri_hmove),
                "vmove_delta_yoy": _delta(cur_vmove, pri_vmove),
            }
        )

    if not records:
        logger.warning("no pitchers passed min_pitches=%d for season %d", min_pitches, season)
        return pd.DataFrame()

    out = pd.DataFrame(records)

    def _raw(vd: Any, hd: Any, vmd: Any) -> float:
        s = 0.0
        if vd is not None and not math.isnan(float(vd)):
            s += -float(vd)  # velo loss → positive raw score
        if hd is not None and not math.isnan(float(hd)):
            s += -abs(float(hd)) * 0.3  # movement loss (either direction)
        if vmd is not None and not math.isnan(float(vmd)):
            s += -float(vmd) * 0.2
        return s

    out["_raw"] = [
        _raw(r["velo_delta_yoy"], r["hmove_delta_yoy"], r["vmove_delta_yoy"])
        for r in out.to_dict("records")
    ]

    def _zscore(g: pd.Series) -> pd.Series:  # type: ignore[type-arg]
        mu = float(g.mean())
        sigma = float(g.std(ddof=1)) if len(g) > 1 else 1.0  # type: ignore[arg-type]
        sigma = sigma if sigma != 0.0 else 1.0
        return (g - mu) / sigma

    out["drift_z"] = out.groupby("pitch_type")["_raw"].transform(_zscore)  # type: ignore[union-attr]
    out = out.drop(columns=["_raw"])
    out = out.sort_values("drift_z", ascending=False).head(top_n)  # type: ignore[call-overload]
    return out.reset_index(drop=True)
