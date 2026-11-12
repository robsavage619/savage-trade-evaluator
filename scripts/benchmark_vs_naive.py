"""D-51 benchmark: V3 context-aware model vs naïve WAR baselines.

Target: captured_war, the WAR acquired players earned for the receiving club
from T through T+5, summed per trade side (R-63). Pass ``war_delta`` as the first
argument to grade the old any-club T+2..T+5 target instead.

Holdout period: 2018-2021. T+5 for 2021 trades is 2026, a partial season.
Train: 2010-2017 for every model, V3 included. V3 is refit here on the
pre-holdout rows; the cached production fit trains through 2022 and has seen the
holdout, so it must not be scored on it.

Both targets have a median of 0 (a third or more of holdout sides are exactly
0), so the MAE-optimal constant is the train median, not the train mean. Both nulls are
reported and the gate is against the better one.

Metrics reported:
  MAE         — posterior mean vs realized target
  CRPS        — calibration-aware scoring rule for the full posterior
  Cov90       — empirical coverage of 90% credible intervals
  P(correct)  — directional accuracy (sign of surplus correct)

Run:
  uv run python scripts/benchmark_vs_naive.py [war_delta]
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd
from scipy.stats import linregress

from savage_trade_evaluator.modeling.metrics import crps_empirical, favoured_side_score
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    fit_v3,
    predict,
)
from savage_trade_evaluator.storage import db

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

HOLDOUT_START = 2018
HOLDOUT_END = 2021
# captured_war is the primary target (R-63); pass war_delta to grade the old one.
OUTCOME = sys.argv[1] if len(sys.argv) > 1 else "captured_war"


def _score_holdout(
    train_df: pd.DataFrame,
    held_out: pd.DataFrame,
) -> tuple[dict[str, float], np.ndarray]:
    """Fit V3 on the pre-holdout rows only and score the holdout rows.

    Args:
        train_df: Pre-holdout rows with realized OUTCOME column.
        held_out: Held-out rows with realized OUTCOME column.

    Returns:
        Dict of MAE, CRPS, cov90, p_correct, n, and the posterior mean per row.
    """
    feat_cols = list(V3_OUTCOME_FEATURES[OUTCOME])
    train = train_df.copy()
    for c in feat_cols:
        col = train[c].astype("float64")
        fill = float(np.nanmean(col.to_numpy())) if col.notna().any() else 0.0
        train[c] = col.fillna(fill)
    fit = fit_v3(train, OUTCOME, tuple(feat_cols))
    scored = pd.DataFrame(index=held_out.index)
    for c in feat_cols:
        if c in held_out.columns:
            scored[c] = held_out[c].astype("float64")
        else:
            scored[c] = float(fit.feature_means.get(c, 0.0))
        scored[c] = scored[c].fillna(float(fit.feature_means.get(c, 0.0)))

    samples = predict(fit, scored)  # (n, n_samples) — subsample for speed
    samples_sub = samples[:, ::10]  # 600 draws

    realized = held_out[OUTCOME].values
    posterior_mean = samples.mean(axis=1)
    p5 = np.percentile(samples, 5, axis=1)
    p95 = np.percentile(samples, 95, axis=1)

    mae = float(np.abs(realized - posterior_mean).mean())
    crps = crps_empirical(realized, samples_sub)
    cov90 = float(np.mean((realized >= p5) & (realized <= p95)))
    # directional: both predict positive or both negative (sign match)
    p_correct = float(np.mean(np.sign(posterior_mean) == np.sign(realized)))

    return {
        "mae": mae,
        "crps": crps,
        "cov90": cov90,
        "p_correct": p_correct,
        "n": len(held_out),
    }, posterior_mean


_SIDES_SQL = f"""
WITH legs AS (
    SELECT trade_event_id, leg_index, to_team_bref AS receiver_bref, trade_season, mlb_player_id
    FROM trade_player_unified
    WHERE to_team_bref IS NOT NULL
      AND trade_season BETWEEN {HOLDOUT_START} AND {HOLDOUT_END}
),
windowed AS (
    SELECT l.trade_event_id, l.receiver_bref,
           COUNT(DISTINCT l.leg_index) AS n_legs,
           SUM(COALESCE(w.war_t_minus_1, 0)) AS prior_war,
           SUM(COALESCE(w.war_t_plus_2, 0) + COALESCE(w.war_t_plus_3, 0)
             + COALESCE(w.war_t_plus_4, 0) + COALESCE(w.war_t_plus_5, 0)) AS window_war
    FROM legs l
    LEFT JOIN trade_player_war_window w USING (trade_event_id, leg_index)
    GROUP BY 1, 2
)
SELECT * FROM windowed
"""


def _decision_report(held_out: pd.DataFrame, pred_mean: np.ndarray) -> None:
    """Print the decision-level score: did the favoured side of a trade win?

    Only trades with exactly two receiving sides in the holdout are scored. Two
    truths are reported: the model's own target (any-team WAR, T+2..T+5) and
    captured value (WAR earned for the receiving club, T..T+5). WAR only; salary
    is not netted out.

    Args:
        held_out: Holdout rows, aligned with ``pred_mean``.
        pred_mean: V3 posterior-mean ``OUTCOME`` per row.
    """
    with db.connect(read_only=True) as conn:
        sides = conn.execute(_SIDES_SQL).df()
    scored = held_out[["trade_event_id", "receiver_bref", "captured_war"]].copy()
    scored["pred_mean"] = pred_mean
    sides = sides.merge(scored, on=["trade_event_id", "receiver_bref"], how="inner")
    # war_delta is a per-leg mean; captured_war is already a side total.
    sides["v3"] = sides["pred_mean"] * (sides["n_legs"] if OUTCOME == "war_delta" else 1)
    sides = sides[sides.groupby("trade_event_id")["receiver_bref"].transform("count") == 2]
    sides = sides.sort_values(["trade_event_id", "receiver_bref"])
    cols = ["v3", "prior_war", "window_war", "captured_war"]
    a = sides.groupby("trade_event_id")[cols].first()
    b = sides.groupby("trade_event_id")[cols].last()
    margin = (a - b).to_numpy(dtype="float64")
    v3_m, prior_m, window_m, captured_m = margin.T

    print("=" * 72)
    print(f"  DECISION LEVEL: favoured side of {len(margin)} two-sided holdout trades")
    print("=" * 72)
    print(f"  {'Picker':<22} {'Truth':<26} {'Win%':>6}  {'±95%':>5}  {'WAR/trade':>9}  {'n':>4}")
    print(f"  {'-' * 68}")
    for truth_name, truth in (
        ("any-team WAR T+2..T+5", window_m),
        ("captured WAR T..T+5", captured_m),
    ):
        for picker_name, pred in (("V3", v3_m), ("More prior-year WAR", prior_m)):
            win, gained, n = favoured_side_score(pred, truth)
            half = 1.96 * (win * (1 - win) / n) ** 0.5 if n else float("nan")
            print(
                f"  {picker_name:<22} {truth_name:<26} {win:>6.1%}  {half:>5.1%}  {gained:>+9.2f}  {n:>4}"
            )
    print("  Coin flip: 50.0% and +0.00 WAR/trade by construction.")
    print()


def main() -> None:
    print("Loading V3 combined dataset…")
    df = assemble_v3_combined()

    held_out = (
        df[(df["trade_season"] >= HOLDOUT_START) & (df["trade_season"] <= HOLDOUT_END)]
        .dropna(subset=[OUTCOME])
        .copy()
    )
    train_df = df[df["trade_season"] < HOLDOUT_START].dropna(subset=[OUTCOME])

    print(
        f"holdout: {len(held_out)} rows ({HOLDOUT_START}–{HOLDOUT_END}), "
        f"mean {OUTCOME}={held_out[OUTCOME].mean():.3f}"
    )
    print(
        f"train:   {len(train_df)} rows (<{HOLDOUT_START}), "
        f"mean {OUTCOME}={train_df[OUTCOME].mean():.3f}"
    )

    realized = held_out[OUTCOME].values
    train_mean = float(train_df[OUTCOME].mean())

    # ── Null: predict training mean ──────────────────────────────────────────
    null_mae = float(np.abs(realized - train_mean).mean())
    null_p_correct = float(np.mean(np.sign(train_mean) == np.sign(realized)))
    train_median = float(np.median(train_df[OUTCOME].to_numpy()))
    median_mae = float(np.abs(realized - train_median).mean())
    median_p_correct = float(np.mean(np.sign(train_median) == np.sign(realized)))
    print(f"holdout sides with {OUTCOME} == 0: {float(np.mean(realized == 0)):.1%}")
    # Distributional null: every row forecast with the training outcome distribution.
    train_y = train_df[OUTCOME].to_numpy(dtype="float64")
    clim_crps = crps_empirical(realized, np.tile(np.sort(train_y), (len(realized), 1)))

    # ── Marcel naive: linear regression on pre-trade WAR quality ─────────────
    train_q = train_df.dropna(subset=["receiver_acquired_player_quality"])
    slope, intercept, r_marcel, _, _ = linregress(
        train_q["receiver_acquired_player_quality"].fillna(0),
        train_q[OUTCOME],
    )
    marcel_pred = intercept + slope * held_out["receiver_acquired_player_quality"].fillna(0)
    marcel_mae = float(np.abs(realized - marcel_pred.values).mean())
    marcel_p_correct = float(np.mean(np.sign(marcel_pred.values) == np.sign(realized)))

    # ── V3 model ──────────────────────────────────────────────────────────────
    print("Fitting V3 on pre-holdout rows and scoring the holdout…")
    v3, v3_pred = _score_holdout(train_df, held_out)

    # ── Report ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(f"  D-51 BENCHMARK: V3 vs Naïve  ({OUTCOME}, holdout {HOLDOUT_START}–{HOLDOUT_END})")
    print("=" * 72)
    print(f"  {'Model':<22} {'MAE':>6}  {'CRPS':>6}  {'Cov90':>6}  {'P(dir)':>6}  {'n':>5}")
    print(f"  {'-' * 65}")
    print(
        f"  {'Null (train mean)':<22} {null_mae:>6.3f}  {'—':>6}  {'—':>6}  {null_p_correct:>6.1%}  {len(held_out):>5}"
    )
    print(
        f"  {'Null (train median)':<22} {median_mae:>6.3f}  {'—':>6}  {'—':>6}  {median_p_correct:>6.1%}  {len(held_out):>5}"
    )
    print(
        f"  {'Climatology (train)':<22} {'—':>6}  {clim_crps:>6.3f}  {'—':>6}  {'—':>6}  {len(held_out):>5}"
    )
    print(
        f"  {'Marcel linear':<22} {marcel_mae:>6.3f}  {'—':>6}  {'—':>6}  {marcel_p_correct:>6.1%}  {len(held_out):>5}"
    )
    print(
        f"  {'V3 (posterior mean)':<22} {v3['mae']:>6.3f}  {v3['crps']:>6.3f}  {v3['cov90']:>6.1%}  {v3['p_correct']:>6.1%}  {v3['n']:>5}"
    )
    print(f"  {'=' * 65}")
    best_null = min(null_mae, median_mae)
    delta_null = best_null - v3["mae"]
    print(
        f"  V3 vs best null: MAE Δ = {delta_null:+.3f} WAR  ({delta_null / best_null:.1%} improvement)"
    )
    delta_marcel = marcel_mae - v3["mae"]
    print(
        f"  V3 vs Marcel:   MAE Δ = {delta_marcel:+.3f} WAR  ({delta_marcel / marcel_mae:.1%} improvement)"
    )
    print(
        f"  V3 vs climatology: CRPS Δ = {clim_crps - v3['crps']:+.3f}  ({(clim_crps - v3['crps']) / clim_crps:.1%} improvement)"
    )
    print(f"  Marcel r² vs train: {r_marcel**2:.3f}")
    print()

    # Go/No-Go
    beat_null = v3["mae"] < best_null
    beat_marcel = v3["mae"] < marcel_mae
    cov_ok = v3["cov90"] >= 0.80
    verdict = "GO" if (beat_null and beat_marcel and cov_ok) else "NO-GO"
    print(f"  Verdict: {verdict}")
    print(f"    beat null:   {beat_null}  beat Marcel: {beat_marcel}  cov90 ≥ 80%: {cov_ok}")
    print()

    _decision_report(held_out, v3_pred)

    sys.exit(0 if verdict == "GO" else 1)


if __name__ == "__main__":
    main()
