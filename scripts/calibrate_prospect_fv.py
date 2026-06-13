"""C4: Build the FV-to-WAR calibration curve and persist to DB.

Fits a linear OLS on (FV, cum_war_5yr) at the player level using
2017-2020 cohort prospects that have been linked to bWAR outcomes.
Stores fitted values + empirical stats in ``prospect_fv_calibration``.

Run after any change to prospect_rankings or bWAR data:

    uv run python scripts/calibrate_prospect_fv.py

The table is small (one row per FV grade) and fast to rebuild (~5 sec).
``valuation/prospect.py`` reads from this table; invalidate its cache
with ``from savage_trade_evaluator.valuation.prospect import invalidate_cache; invalidate_cache()``
after re-running this script if the process is still live.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("calibrate_fv")

import numpy as np
import pandas as pd
from scipy import stats

from savage_trade_evaluator.storage import db
from savage_trade_evaluator.storage.schemas import initialize as initialize_schema

COHORT_START = 2017
COHORT_END = 2020
WAR_WINDOW = 5  # T+1 through T+5
MIN_GRADE_N = 3  # need at least this many observations to include a grade


def _build_cohort(conn: object) -> pd.DataFrame:
    return conn.execute(  # type: ignore[attr-defined]
        f"""
        WITH cohort AS (
            SELECT DISTINCT
                pr.rank_year,
                pr.fv,
                cr.mlb_player_id
            FROM prospect_rankings pr
            JOIN chadwick_register cr
                ON cr.fangraphs_id = pr.fangraphs_player_id
            WHERE pr.rank_year BETWEEN {COHORT_START} AND {COHORT_END}
              AND pr.fv IS NOT NULL
        ),
        bwar_annual AS (
            SELECT mlb_id, year_id, SUM(war) AS war
            FROM (
                SELECT mlb_id, year_id, war FROM bwar_batting
                UNION ALL
                SELECT mlb_id, year_id, war FROM bwar_pitching
            ) combined
            GROUP BY mlb_id, year_id
        ),
        with_outcomes AS (
            SELECT
                c.rank_year,
                c.fv,
                c.mlb_player_id,
                SUM(CASE
                        WHEN ba.year_id BETWEEN c.rank_year + 1
                                             AND c.rank_year + {WAR_WINDOW}
                        THEN ba.war
                        ELSE 0
                    END
                ) AS cum_war_5yr
            FROM cohort c
            LEFT JOIN bwar_annual ba
                ON ba.mlb_id = c.mlb_player_id
            GROUP BY c.rank_year, c.fv, c.mlb_player_id
        )
        SELECT rank_year, fv, mlb_player_id, COALESCE(cum_war_5yr, 0) AS cum_war_5yr
        FROM with_outcomes
        """
    ).df()


def _fit_calibration(df: pd.DataFrame) -> pd.DataFrame:
    """Fit OLS linear model and return per-grade calibration rows."""
    # Clip extreme outliers before fitting (injury/bust seasons don't reflect FV signal)
    wars = df["cum_war_5yr"]
    p5, p95 = float(np.percentile(wars, 5)), float(np.percentile(wars, 95))
    df_fit = df.copy()
    df_fit["cum_war_5yr"] = df_fit["cum_war_5yr"].clip(p5, p95)

    slope, intercept, r, p, stderr = stats.linregress(df_fit["fv"], df_fit["cum_war_5yr"])
    logger.info(
        "OLS fit: WAR = %.4f + %.4f * FV  |  r=%.3f  p=%.4f  stderr=%.4f",
        intercept, slope, r, p, stderr,
    )

    # Residual sigma for p10/p90 bounds (assumes normal residuals).
    predicted = intercept + slope * df_fit["fv"]
    resid_sigma = float(np.std(df_fit["cum_war_5yr"] - predicted))
    from scipy.stats import norm
    z10 = float(norm.ppf(0.10))
    z90 = float(norm.ppf(0.90))

    # Empirical stats per FV grade.
    grp = (
        df.groupby("fv")["cum_war_5yr"]
        .agg(n="count", mean="mean", median="median", std="std")
        .reset_index()
    )
    grp = grp[grp["n"] >= MIN_GRADE_N].copy()

    grp["fitted_war_5yr"] = (intercept + slope * grp["fv"]).clip(lower=0.0)
    grp["fitted_war_p10"] = (grp["fitted_war_5yr"] + z10 * resid_sigma).clip(lower=0.0)
    grp["fitted_war_p90"] = (grp["fitted_war_5yr"] + z90 * resid_sigma).clip(lower=0.0)

    return grp.rename(columns={
        "mean": "mean_war_5yr", "median": "median_war_5yr",
        "std": "std_war_5yr", "n": "n_comparables",
    })


def _persist(calibration: pd.DataFrame, conn: object) -> None:
    conn.execute("DELETE FROM prospect_fv_calibration")  # type: ignore[attr-defined]
    for _, row in calibration.iterrows():
        conn.execute(  # type: ignore[attr-defined]
            """
            INSERT INTO prospect_fv_calibration
                (fv, n_comparables, mean_war_5yr, median_war_5yr, std_war_5yr,
                 fitted_war_5yr, fitted_war_p10, fitted_war_p90,
                 cohort_start, cohort_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                int(row["fv"]),
                int(row["n_comparables"]),
                float(row["mean_war_5yr"]),
                float(row["median_war_5yr"]),
                float(row["std_war_5yr"]) if not np.isnan(row["std_war_5yr"]) else 0.0,
                float(row["fitted_war_5yr"]),
                float(row["fitted_war_p10"]),
                float(row["fitted_war_p90"]),
                COHORT_START,
                COHORT_END,
            ],
        )
    logger.info("prospect_fv_calibration: %d grades written", len(calibration))


def _print_table(calibration: pd.DataFrame) -> None:
    print()
    print("=" * 75)
    print(f"PROSPECT FV CALIBRATION — cohort {COHORT_START}-{COHORT_END}  T+1...T+{WAR_WINDOW} WAR")
    print("=" * 75)
    hdr = f"  {'FV':>4}  {'N':>5}  {'mean WAR':>10}  {'median':>8}"
    hdr += f"  {'fitted':>8}  {'p10':>6}  {'p90':>6}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for _, r in calibration.sort_values("fv").iterrows():
        print(
            f"  {int(r.fv):>4}  {int(r.n_comparables):>5}  "
            f"{r.mean_war_5yr:>10.2f}  {r.median_war_5yr:>8.2f}  "
            f"{r.fitted_war_5yr:>8.2f}  {r.fitted_war_p10:>6.2f}  {r.fitted_war_p90:>6.2f}"
        )
    print("=" * 75)
    print()


def main() -> None:
    with db.connect() as conn:
        initialize_schema(conn)
        logger.info("Building cohort outcomes for rank_years %d-%d...", COHORT_START, COHORT_END)
        df = _build_cohort(conn)
        n_with_war = int((df["cum_war_5yr"] != 0).sum())
        logger.info("Cohort: %d player-season rows, %d with WAR outcomes", len(df), n_with_war)

        if len(df) < 10:
            logger.error(
                "Too few cohort rows (%d) — check prospect_rankings and chadwick_register linkage",
                len(df),
            )
            sys.exit(1)

        calibration = _fit_calibration(df)
        _persist(calibration, conn)

    _print_table(calibration)


if __name__ == "__main__":
    main()
