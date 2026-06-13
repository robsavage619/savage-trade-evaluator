"""D-51 benchmark: V3 context-aware model vs naïve WAR baselines.

Holdout period: 2018-2021 (fully realized 3yr outcome windows).
Train: 2010-2017 (V3 production fit uses 2010-2022; this script uses an
explicit pre-holdout split to avoid leakage for the null/Marcel comparators).

Metrics reported:
  MAE         — posterior mean vs realized war_delta
  CRPS        — calibration-aware scoring rule for the full posterior
  Cov90       — empirical coverage of 90% credible intervals
  P(correct)  — directional accuracy (sign of surplus correct)

Run:
  uv run python scripts/benchmark_vs_naive.py
"""

from __future__ import annotations

import logging
import sys

import numpy as np
import pandas as pd
from scipy.stats import linregress

from savage_trade_evaluator.modeling.production_fit import get_fit
from savage_trade_evaluator.modeling.v3 import assemble_v3_combined, predict

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

HOLDOUT_START = 2018
HOLDOUT_END = 2021
OUTCOME = "war_delta"


def crps_sorted(samples: np.ndarray, obs: np.ndarray) -> float:
    """CRPS via the sorted-samples identity (O(n m log m), no pairwise).

    Args:
        samples: (n_obs, n_samples) posterior draws.
        obs: (n_obs,) realized outcomes.

    Returns:
        Mean CRPS across observations.
    """
    s = np.sort(samples, axis=1)
    m = s.shape[1]
    i = np.arange(1, m + 1, dtype=float)
    step = (2.0 * i / m) - 1.0
    residuals = s - obs[:, None]
    indicator = (obs[:, None] <= s).astype(float)
    # CRPS = E|X - y| + (contribution from step function vs indicator)
    crps_per_obs = np.mean(np.abs(residuals), axis=1) - np.mean(step * (s - obs[:, None] - indicator * (s - obs[:, None])), axis=1)
    return float(crps_per_obs.mean())


def _score_holdout(
    df: pd.DataFrame,
    held_out: pd.DataFrame,
) -> dict[str, float]:
    """Load production fit and score the holdout rows.

    Args:
        df: Full combined DataFrame (for feature_means fallback).
        held_out: Held-out rows with realized OUTCOME column.

    Returns:
        Dict of MAE, CRPS, cov90, p_correct, n.
    """
    fit = get_fit(OUTCOME)
    feat_cols = list(fit.feature_cols)
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
    crps = crps_sorted(samples_sub, realized)
    cov90 = float(np.mean((realized >= p5) & (realized <= p95)))
    # directional: both predict positive or both negative (sign match)
    p_correct = float(np.mean(np.sign(posterior_mean) == np.sign(realized)))

    return {
        "mae": mae,
        "crps": crps,
        "cov90": cov90,
        "p_correct": p_correct,
        "n": len(held_out),
    }


def main() -> None:
    print("Loading V3 combined dataset…")
    df = assemble_v3_combined()

    held_out = (
        df[
            (df["trade_season"] >= HOLDOUT_START)
            & (df["trade_season"] <= HOLDOUT_END)
        ]
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

    # ── Marcel naive: linear regression on pre-trade WAR quality ─────────────
    train_q = train_df.dropna(subset=["receiver_acquired_player_quality"])
    slope, intercept, r_marcel, _, _ = linregress(
        train_q["receiver_acquired_player_quality"].fillna(0),
        train_q[OUTCOME],
    )
    marcel_pred = intercept + slope * held_out["receiver_acquired_player_quality"].fillna(0)
    marcel_mae = float(np.abs(realized - marcel_pred.values).mean())
    marcel_p_correct = float(
        np.mean(np.sign(marcel_pred.values) == np.sign(realized))
    )

    # ── V3 model ──────────────────────────────────────────────────────────────
    print("Scoring V3 posteriors on holdout…")
    v3 = _score_holdout(df, held_out)

    # ── Report ────────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(f"  D-51 BENCHMARK: V3 vs Naïve  ({OUTCOME}, holdout {HOLDOUT_START}–{HOLDOUT_END})")
    print("=" * 72)
    print(
        f"  {'Model':<22} {'MAE':>6}  {'CRPS':>6}  {'Cov90':>6}  {'P(dir)':>6}  {'n':>5}"
    )
    print(f"  {'-'*65}")
    print(
        f"  {'Null (train mean)':<22} {null_mae:>6.3f}  {'—':>6}  {'—':>6}  {null_p_correct:>6.1%}  {len(held_out):>5}"
    )
    print(
        f"  {'Marcel linear':<22} {marcel_mae:>6.3f}  {'—':>6}  {'—':>6}  {marcel_p_correct:>6.1%}  {len(held_out):>5}"
    )
    print(
        f"  {'V3 (posterior mean)':<22} {v3['mae']:>6.3f}  {v3['crps']:>6.3f}  {v3['cov90']:>6.1%}  {v3['p_correct']:>6.1%}  {v3['n']:>5}"
    )
    print(f"  {'='*65}")
    delta_null = null_mae - v3["mae"]
    print(
        f"  V3 vs Null:     MAE Δ = {delta_null:+.3f} WAR  ({delta_null/null_mae:.1%} improvement)"
    )
    delta_marcel = marcel_mae - v3["mae"]
    print(
        f"  V3 vs Marcel:   MAE Δ = {delta_marcel:+.3f} WAR  ({delta_marcel/marcel_mae:.1%} improvement)"
    )
    print(f"  Marcel r² vs train: {r_marcel**2:.3f}")
    print()

    # Go/No-Go
    beat_null = v3["mae"] < null_mae
    beat_marcel = v3["mae"] < marcel_mae
    cov_ok = v3["cov90"] >= 0.80
    verdict = "GO" if (beat_null and beat_marcel and cov_ok) else "NO-GO"
    print(f"  Verdict: {verdict}")
    print(f"    beat null:   {beat_null}  beat Marcel: {beat_marcel}  cov90 ≥ 80%: {cov_ok}")
    print()

    sys.exit(0 if verdict == "GO" else 1)


if __name__ == "__main__":
    main()
