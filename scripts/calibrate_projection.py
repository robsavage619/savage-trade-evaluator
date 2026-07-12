"""Backtest-calibrate the projection shrinkage strength (regression_pt).

For every pitcher-season Y with a near-full following season Y+1, project the
full-season WAR rate from {Y-2, Y-1, Y} and compare to the actual Y+1 WAR. Sweep
``regression_pt`` for the out-of-sample minimum, benchmarked against the naive
"use last season's WAR" rule the production surface used (the closer-trade bug).

Run:
    uv run python scripts/calibrate_projection.py
"""

from __future__ import annotations

import logging
from collections import defaultdict

from savage_trade_evaluator.modeling.projection import (
    BATTER_BASELINE_WAR,
    FULL_SEASON_PA,
    RELIEVER_BASELINE_WAR,
    STARTER_BASELINE_WAR,
    SeasonWar,
    playing_time_fraction,
    project_war,
)
from savage_trade_evaluator.storage.db import connect

logger = logging.getLogger(__name__)

TARGET_MIN_PT = 0.8  # Y+1 must be a near-full season to be a clean target.
FIRST_TARGET_YEAR = 2011
LAST_TARGET_YEAR = 2024
REGRESSION_GRID = (0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0)


def _load_pitcher_panel() -> dict[int, dict[int, tuple[float, float, bool]]]:
    """Return {mlb_id: {year: (war, pt_fraction, is_reliever)}} for pitchers."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT mlb_id, year_id, SUM(g) AS g, SUM(gs) AS gs, SUM(war) AS war
            FROM bwar_pitching
            WHERE year_id BETWEEN 2008 AND 2024
            GROUP BY mlb_id, year_id
            """
        ).fetchall()

    panel: dict[int, dict[int, tuple[float, float, bool]]] = defaultdict(dict)
    for mlb_id, year_id, g, gs, war in rows:
        g_i = int(g or 0)
        gs_i = int(gs or 0)
        is_rel = gs_i < g_i / 2
        pt = playing_time_fraction(g_i, gs_i, is_reliever=is_rel)
        panel[int(mlb_id)][int(year_id)] = (float(war or 0.0), pt, is_rel)
    return panel


def _load_batter_panel() -> dict[int, dict[int, tuple[float, float, bool]]]:
    """Return {mlb_id: {year: (war, pt_fraction, is_reliever=False)}} for hitters."""
    with connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT mlb_id, year_id, SUM(pa) AS pa, SUM(war) AS war
            FROM bwar_batting
            WHERE year_id BETWEEN 2008 AND 2024 AND is_pitcher = false
            GROUP BY mlb_id, year_id
            """
        ).fetchall()

    panel: dict[int, dict[int, tuple[float, float, bool]]] = defaultdict(dict)
    for mlb_id, year_id, pa, war in rows:
        pt = int(pa or 0) / FULL_SEASON_PA
        panel[int(mlb_id)][int(year_id)] = (float(war or 0.0), pt, False)
    return panel


def _build_samples(
    panel: dict[int, dict[int, tuple[float, float, bool]]],
    batter_baseline: float | None = None,
) -> list[tuple[list[SeasonWar], float, float, bool]]:
    """Return (input_seasons, target_war, baseline, target_is_reliever) samples.

    When ``batter_baseline`` is set the panel is treated as hitters (single
    baseline, is_reliever=False); otherwise pitcher role baselines are used.
    """
    samples: list[tuple[list[SeasonWar], float, float, bool]] = []
    for by_year in panel.values():
        for y in range(FIRST_TARGET_YEAR - 1, LAST_TARGET_YEAR):
            target = by_year.get(y + 1)
            if target is None:
                continue
            target_war, target_pt, _ = target
            if target_pt < TARGET_MIN_PT:
                continue
            inputs: list[SeasonWar] = []
            roles: list[bool] = []
            for offset in (0, 1, 2):  # Y, Y-1, Y-2 (most recent first)
                s = by_year.get(y - offset)
                if s is None:
                    continue
                war_s, pt_s, rel_s = s
                inputs.append(SeasonWar(y - offset, war_s, pt_s, rel_s))
                roles.append(rel_s)
            if not inputs:
                continue
            if batter_baseline is not None:
                samples.append((inputs, target_war, batter_baseline, False))
            else:
                is_rel = sum(1 for rel in roles if rel) / len(roles) >= 0.5
                baseline = RELIEVER_BASELINE_WAR if is_rel else STARTER_BASELINE_WAR
                samples.append((inputs, target_war, baseline, is_rel))
    return samples


def _score(preds: list[float], actuals: list[float]) -> tuple[float, float, float]:
    n = len(preds)
    errs = [p - a for p, a in zip(preds, actuals, strict=True)]
    mae = sum(abs(e) for e in errs) / n
    rmse = (sum(e * e for e in errs) / n) ** 0.5
    bias = sum(errs) / n
    return mae, rmse, bias


def _sweep(samples: list[tuple[list[SeasonWar], float, float, bool]], label: str) -> None:
    """Print the naive baseline + regression_pt sweep for one sample set."""
    logger.info(
        "=== %s: %d samples (Y -> Y+1, target pt>=%.1f) ===", label, len(samples), TARGET_MIN_PT
    )
    actuals = [t for _, t, _, _ in samples]
    naive = [inp[0].war for inp, _, _, _ in samples]
    n_mae, n_rmse, n_bias = _score(naive, actuals)
    logger.info("naive (last-season WAR):   MAE=%.3f  RMSE=%.3f  bias=%+.3f", n_mae, n_rmse, n_bias)

    best = None
    logger.info(f"{'regression_pt':>13} {'MAE':>7} {'RMSE':>7} {'bias':>8}   vs naive MAE")
    for rpt in REGRESSION_GRID:
        preds = [project_war(inp, base, regression_pt=rpt) for inp, _, base, _ in samples]
        mae, rmse, bias = _score(preds, actuals)
        improve = (n_mae - mae) / n_mae * 100.0
        marker = ""
        if best is None or mae < best[1]:
            best = (rpt, mae, rmse, bias)
            marker = "  <= best"
        logger.info("%13.1f %7.3f %7.3f %+8.3f   %+5.1f%%%s", rpt, mae, rmse, bias, improve, marker)

    assert best is not None
    logger.info(
        "BEST regression_pt=%.1f  MAE=%.3f (%.1f%% better than naive)\n",
        best[0],
        best[1],
        (n_mae - best[1]) / n_mae * 100.0,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _sweep(_build_samples(_load_pitcher_panel()), "PITCHERS")
    _sweep(_build_samples(_load_batter_panel(), batter_baseline=BATTER_BASELINE_WAR), "BATTERS")


if __name__ == "__main__":
    main()
