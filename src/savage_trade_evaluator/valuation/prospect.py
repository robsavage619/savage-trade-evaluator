"""C4: FV-to-WAR calibration for prospect packages in trade evaluation.

Converts a FanGraphs Future Value (FV) grade to an expected cumulative WAR
over a 5-year post-ranking window, with empirical uncertainty bounds derived
from 2017-2020 cohort outcomes.

Calibration is a simple OLS linear fit on (FV, cum_war_5yr) at the player
level, with residual sigma used for the p10/p90 bounds. Monotonicity is
guaranteed by the linear model. Full hierarchical regression is Phase 3.

Primary entry point::

    from savage_trade_evaluator.valuation.prospect import score_prospect
    score = score_prospect(fv=60)
    # score.fitted_war_5yr → expected cumulative WAR over 5 seasons

The calibration table must be populated first via
``scripts/calibrate_prospect_fv.py`` — this module reads from DB, not
re-derives from raw bWAR on every call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

# Supported FV grades on the FanGraphs 20-80 scale.
VALID_FV_GRADES = (45, 50, 55, 60, 65, 70, 75, 80)

# Cohort used for calibration.
CALIBRATION_COHORT_START = 2017
CALIBRATION_COHORT_END = 2020


@dataclass(frozen=True, slots=True)
class ProspectScore:
    """Calibrated WAR expectation for a prospect at a given FV grade.

    Attributes:
        fv: FanGraphs Future Value grade (20-80 scale).
        fitted_war_5yr: Model-fitted expected cumulative WAR over 5 seasons.
        war_p10: Empirical 10th-percentile bound (OLS residual sigma, fitted).
        war_p90: Empirical 90th-percentile bound.
        n_comparables: Number of comparable prospects used to fit this grade.
        mean_war_5yr: Raw empirical mean for this FV grade.
        median_war_5yr: Raw empirical median.
    """

    fv: int
    fitted_war_5yr: float
    war_p10: float
    war_p90: float
    n_comparables: int
    mean_war_5yr: float
    median_war_5yr: float


@lru_cache(maxsize=1)
def _load_calibration() -> dict[int, ProspectScore]:
    """Load prospect_fv_calibration table into memory (cached).

    Returns:
        Dict mapping FV grade → ProspectScore. Empty if table not populated.
    """
    with db.connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT fv, n_comparables, mean_war_5yr, median_war_5yr,
                   fitted_war_5yr, fitted_war_p10, fitted_war_p90
            FROM prospect_fv_calibration
            ORDER BY fv
            """
        ).fetchall()

    if not rows:
        logger.warning(
            "prospect_fv_calibration table is empty — run scripts/calibrate_prospect_fv.py first"
        )
        return {}

    return {
        int(r[0]): ProspectScore(
            fv=int(r[0]),
            n_comparables=int(r[1]),
            mean_war_5yr=float(r[2]),
            median_war_5yr=float(r[3]),
            fitted_war_5yr=float(r[4]),
            war_p10=float(r[5]),
            war_p90=float(r[6]),
        )
        for r in rows
    }


def score_prospect(fv: int) -> ProspectScore:
    """Return the calibrated WAR expectation for a prospect at the given FV grade.

    Reads from the pre-built ``prospect_fv_calibration`` table (populated by
    ``scripts/calibrate_prospect_fv.py``). If the exact grade is not in the
    table (e.g. FV 45 before calibration), interpolates linearly between
    adjacent grades. Returns a zero-value sentinel if the calibration table
    is empty.

    Args:
        fv: FanGraphs Future Value grade (typically 45-80 in 5-point steps).

    Returns:
        ``ProspectScore`` with fitted WAR expectation and uncertainty bounds.

    Raises:
        ValueError: If fv is outside [40, 85].
    """
    if not (40 <= fv <= 85):
        raise ValueError(f"fv={fv} is outside the valid range [40, 85]")

    table = _load_calibration()
    if not table:
        logger.warning("score_prospect: calibration table empty; returning zero sentinel")
        return ProspectScore(
            fv=fv,
            fitted_war_5yr=0.0,
            war_p10=0.0,
            war_p90=0.0,
            n_comparables=0,
            mean_war_5yr=0.0,
            median_war_5yr=0.0,
        )

    if fv in table:
        return table[fv]

    # Linear interpolation between adjacent grades.
    grades = sorted(table.keys())
    lo = max((g for g in grades if g <= fv), default=grades[0])
    hi = min((g for g in grades if g >= fv), default=grades[-1])
    if lo == hi:
        return table[lo]

    t = (fv - lo) / (hi - lo)
    lo_s, hi_s = table[lo], table[hi]
    return ProspectScore(
        fv=fv,
        fitted_war_5yr=lo_s.fitted_war_5yr + t * (hi_s.fitted_war_5yr - lo_s.fitted_war_5yr),
        war_p10=lo_s.war_p10 + t * (hi_s.war_p10 - lo_s.war_p10),
        war_p90=lo_s.war_p90 + t * (hi_s.war_p90 - lo_s.war_p90),
        n_comparables=min(lo_s.n_comparables, hi_s.n_comparables),
        mean_war_5yr=lo_s.mean_war_5yr + t * (hi_s.mean_war_5yr - lo_s.mean_war_5yr),
        median_war_5yr=lo_s.median_war_5yr + t * (hi_s.median_war_5yr - lo_s.median_war_5yr),
    )


def invalidate_cache() -> None:
    """Clear the in-process calibration cache (call after re-running calibration)."""
    _load_calibration.cache_clear()
