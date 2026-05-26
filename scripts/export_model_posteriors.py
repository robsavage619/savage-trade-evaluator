"""Export real V3 posteriors to JSON for the frontend.

Fits V3 on both ``surplus_wins`` (wins above cost basis — the headline metric)
and ``dollar_surplus`` (dollars, secondary anchor) on the 2010-2020 training
window, predicts held-out 2021-2024 trades, and writes:

- ``posteriors.json``  — curated featured cards + walk-forward scoreboard
- ``by_trade.json``    — compact per-trade lookup for the Trade Workspace

Each card/entry carries both wins and dollar posteriors so the frontend can
headline wins and use dollars as the anchor (Phase C wins-first presentation).

Run:
    uv run python scripts/export_model_posteriors.py
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    _SIGNED_LOG_OUTCOMES,
    _inv_signed_log,
    _split_and_impute,
    assemble_v3_combined,
    backtest_outcome_v3,
    predict,
)
from savage_trade_evaluator.modeling.v3_cv import MIN_TEST_N, walk_forward_splits
from savage_trade_evaluator.storage.db import connect

# Reuse the validated R-58 fold comparison (same methodology that produced the
# D-39/D-41 thesis numbers) rather than re-deriving a single-split baseline.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from r58_baseline_comparison import run_fold_comparison

logger = logging.getLogger(__name__)

OUTCOME = "dollar_surplus"  # dollar anchor (secondary)
WINS_OUTCOME = "surplus_wins"  # wins headline (primary, Phase B)
TRAIN_END = 2020
TEST_END = 2024
OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "data" / "model"

# Curated held-out trades to feature, each tagged with its narrative role:
#   "covered"   — realized outcome fell inside the 90% credible interval
#   "tail_miss" — a known limitation: the model shrinks extreme-tail blockbusters
#                 toward the regime mean (CLAUDE.md validation philosophy). Shown
#                 deliberately so the demo is honest about where V3 fails.
FEATURED: tuple[tuple[int, str, str], ...] = (
    (808316, "CHC", "covered"),  # Kyle Tucker → Cubs, 2024 (headline)
    (768021, "SDP", "covered"),  # Luis Arraez → Padres, 2024
    (739097, "BAL", "covered"),  # Corbin Burnes → Orioles, 2024
    (642337, "SDP", "tail_miss"),  # Juan Soto + Josh Bell → Padres, 2022 (under-predicted)
)

# How many raw posterior draws to embed per card for an empirical violin.
N_DRAWS_EMBED = 400


def _player_labels() -> dict[tuple[int, str], list[str]]:
    """Map (trade_event_id, receiver_bref) → acquired player names."""
    with connect(read_only=True) as con:
        rows = con.execute(
            """
            SELECT trade_event_id, to_team_bref AS receiver_bref,
                   from_team_bref AS sender_bref, player_name
            FROM trade_player_unified
            WHERE trade_season BETWEEN 2010 AND 2024
            """,
        ).df()
    labels: dict[tuple[int, str], list[str]] = {}
    senders: dict[tuple[int, str], str] = {}
    for r in rows.itertuples():
        key = (int(r.trade_event_id), r.receiver_bref)
        labels.setdefault(key, [])
        # NULL player names arrive as float nan (which is truthy) — guard on str.
        if isinstance(r.player_name, str) and r.player_name not in labels[key]:
            labels[key].append(r.player_name)
        if isinstance(r.sender_bref, str):
            senders[key] = r.sender_bref
    _player_labels._senders = senders  # type: ignore[attr-defined]
    return labels


def _walk_forward_comparison(
    outcome: str,
    combined: pd.DataFrame,
) -> dict[str, object]:
    """Validated walk-forward CV comparison (R-58 methodology, D-39/D-41 numbers).

    Per 2-year fold, scores three models by CRPS (lower is better):
      * context-aware    — full V3 model (ALL_FEATURES, receiving-team context)
      * player-quality    — single feature (receiver_acquired_player_quality)
      * intercept-only    — Bayesian "predict the mean" floor

    Returns per-fold rows plus aggregate skill, computed two honest ways:
    vs player-quality (the thesis win) and vs intercept-only (parity on raw $).
    The structural-break fold (2017-18) is flagged, not hidden.
    """
    feature_cols = V3_OUTCOME_FEATURES[outcome]
    min_n = MIN_TEST_N.get(outcome, 50)
    splits = walk_forward_splits(outcome, combined)

    folds = []
    for sp in splits:
        r = run_fold_comparison(
            outcome,
            feature_cols,
            combined=combined,
            train_end=sp.train_end,
            test_end=sp.test_end,
            train_start=sp.train_start,
            min_n=min_n,
        )
        # The 2017-18 fold is the documented structural break (D-40).
        is_break = sp.test_start <= 2017 <= sp.test_end
        folds.append(
            {
                "label": f"{sp.test_start}–{sp.test_end}",  # noqa: RUF001
                "n_test": int(r["n_test"]),
                "crps_context": round(float(r["crps_model"]), 1),
                "crps_quality": round(float(r["crps_quality"]), 1),
                "crps_intercept": round(float(r["crps_intercept"]), 1),
                "skill_vs_quality": round(float(r["skill_model_vs_quality"]), 4),
                "skill_vs_intercept": round(float(r["skill_vs_bayes_intercept"]), 4),
                "structural_break": is_break,
            }
        )

    stable = [f for f in folds if not f["structural_break"]]

    def _mean(rows: list[dict], key: str) -> float:
        vals = [r[key] for r in rows if r[key] == r[key]]  # drop NaN
        return round(sum(vals) / len(vals), 4) if vals else float("nan")

    return {
        "folds": folds,
        "mean_skill_vs_quality": _mean(folds, "skill_vs_quality"),
        "mean_skill_vs_intercept": _mean(folds, "skill_vs_intercept"),
        "mean_skill_vs_quality_ex_break": _mean(stable, "skill_vs_quality"),
        "mean_skill_vs_intercept_ex_break": _mean(stable, "skill_vs_intercept"),
    }


def _summarize(draws: np.ndarray, use_median: bool = False) -> dict[str, object]:
    """Posterior summary for a single trade's predictive draws (1D array).

    use_median=True for Cauchy-dominated outcomes (e.g. dollar_surplus after
    signed-log transform) where mean is unstable.
    """
    rng = np.random.default_rng(137)
    embed = (
        draws if draws.size <= N_DRAWS_EMBED else rng.choice(draws, N_DRAWS_EMBED, replace=False)
    )
    central = float(np.median(draws)) if use_median else float(draws.mean())
    return {
        "mean": central,
        "sd": float(draws.std()),
        "p05": float(np.percentile(draws, 5)),
        "p25": float(np.percentile(draws, 25)),
        "p50": float(np.percentile(draws, 50)),
        "p75": float(np.percentile(draws, 75)),
        "p95": float(np.percentile(draws, 95)),
        "draws": [round(float(x), 1) for x in sorted(embed)],
    }


def main() -> None:
    """Fit V3 surplus_wins + dollar_surplus, score held-out trades, write frontend JSON."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    combined = assemble_v3_combined()

    # --- fit both outcome models ---
    for outcome, label in ((WINS_OUTCOME, "wins"), (OUTCOME, "dollars")):
        logger.info(
            "Fitting V3 %s (%s) on %d-%d, scoring %d-%d ...",
            outcome,
            label,
            2010,
            TRAIN_END,
            TRAIN_END + 1,
            TEST_END,
        )
    result_w = backtest_outcome_v3(
        WINS_OUTCOME,
        train_end_season=TRAIN_END,
        test_end_season=TEST_END,
        combined=combined,
    )
    result_d = backtest_outcome_v3(
        OUTCOME,
        train_end_season=TRAIN_END,
        test_end_season=TEST_END,
        combined=combined,
    )
    for res, label in ((result_w, WINS_OUTCOME), (result_d, OUTCOME)):
        logger.info(
            "  %s: train_n=%d test_n=%d  CRPS=%.3f  coverage_90=%.2f",
            label,
            res.train_n,
            res.test_n,
            res.test_crps,
            res.coverage_90,
        )

    cols_w = V3_OUTCOME_FEATURES[WINS_OUTCOME]
    cols_d = V3_OUTCOME_FEATURES[OUTCOME]
    _, test_w = _split_and_impute(WINS_OUTCOME, cols_w, TRAIN_END, TEST_END)
    train_d, test_d = _split_and_impute(OUTCOME, cols_d, TRAIN_END, TEST_END)

    logger.info("Running walk-forward comparison (R-58) for both outcomes ...")
    comparison_w = _walk_forward_comparison(WINS_OUTCOME, combined)
    comparison_d = _walk_forward_comparison(OUTCOME, combined)
    for comp, name in ((comparison_w, WINS_OUTCOME), (comparison_d, OUTCOME)):
        logger.info(
            "  %s: skill vs quality=%+.1f%% (ex-break %+.1f%%) · vs intercept=%+.1f%% (ex-break %+.1f%%)",  # noqa: E501
            name,
            comp["mean_skill_vs_quality"] * 100,
            comp["mean_skill_vs_quality_ex_break"] * 100,
            comp["mean_skill_vs_intercept"] * 100,
            comp["mean_skill_vs_intercept_ex_break"] * 100,
        )

    labels = _player_labels()
    senders: dict[tuple[int, str], str] = _player_labels._senders  # type: ignore[attr-defined]

    cred = result_d.credible_features
    credible = cred[cred["credible"]].head(8)
    credible_features = [
        {
            "feature": r.feature,
            "beta": round(float(r.mean_beta), 4),
            "directional_mass": round(float(r.directional_mass), 3),
        }
        for r in credible.itertuples()
    ]

    # Index wins test rows by (event_id, receiver_bref) for fast lookup.
    wins_index: dict[tuple[int, str], int] = {
        (int(r.trade_event_id), r.receiver_bref): i for i, r in enumerate(test_w.itertuples())
    }
    wins_preds_all = predict(result_w.fit, test_w)  # (n_rows_w, n_samples)

    cards = []
    for event_id, recv, role in FEATURED:
        mask_d = (test_d["trade_event_id"] == event_id) & (test_d["receiver_bref"] == recv)
        if not mask_d.any():
            logger.warning("  SKIP %s/%s — not in dollar held-out split", event_id, recv)
            continue
        row_d = test_d[mask_d]
        _draws_d_raw = predict(result_d.fit, row_d)[0]
        draws_d = _inv_signed_log(_draws_d_raw) if OUTCOME in _SIGNED_LOG_OUTCOMES else _draws_d_raw
        realized_d = float(row_d[OUTCOME].iloc[0])
        summary_d = _summarize(draws_d, use_median=(OUTCOME in _SIGNED_LOG_OUTCOMES))
        in_ci_d = summary_d["p05"] <= realized_d <= summary_d["p95"]

        wins_idx = wins_index.get((event_id, recv))
        if wins_idx is not None:
            draws_w = wins_preds_all[wins_idx]
            realized_w = float(test_w.iloc[wins_idx][WINS_OUTCOME])
            summary_w = _summarize(draws_w)
            in_ci_w = summary_w["p05"] <= realized_w <= summary_w["p95"]
        else:
            summary_w, realized_w, in_ci_w = None, None, None

        cards.append(
            {
                "trade_event_id": int(event_id),
                "receiver_bref": recv,
                "sender_bref": senders.get((event_id, recv)),
                "season": int(row_d["trade_season"].iloc[0]),
                "role": role,
                "acquired_players": labels.get((event_id, recv), []),
                # wins headline (surplus_wins posterior)
                "wins_posterior": summary_w,
                "wins_realized": round(realized_w, 2) if realized_w is not None else None,
                "wins_realized_in_90ci": bool(in_ci_w) if in_ci_w is not None else None,
                # dollar anchor (dollar_surplus posterior)
                "posterior": summary_d,
                "realized": round(realized_d, 1),
                "realized_in_90ci": bool(in_ci_d),
            }
        )
        w_str = (
            f"{summary_w['mean']:+.2f}W [{summary_w['p05']:.2f},{summary_w['p95']:.2f}]"
            if summary_w
            else "n/a"
        )
        logger.info(
            "  %s/%s  wins=%s  $pred=$%.1fM  realized=$%.1fM  in90CI=%s",
            event_id,
            recv,
            w_str,
            summary_d["mean"] / 1e6,
            realized_d / 1e6,
            in_ci_d,
        )

    # Per-trade lookup — compact wins + dollar summary per trade.
    # Wins rows keyed separately then merged; missing wins → nulls in entry.
    by_trade: dict[str, dict[str, object]] = {}
    wins_pred_map: dict[str, tuple[float, float, float, float, float, float]] = {}
    wins_full_preds = predict(result_w.fit, test_w)
    for i, r in enumerate(test_w.itertuples()):
        d = wins_full_preds[i]
        p05, p50, p95 = (float(np.percentile(d, q)) for q in (5, 50, 95))
        wins_pred_map[f"{int(r.trade_event_id)}:{r.receiver_bref}"] = (
            round(float(d.mean()), 3),
            round(float(d.std()), 3),
            round(p05, 3),
            round(p50, 3),
            round(p95, 3),
            round(float(getattr(r, WINS_OUTCOME)), 3),
        )
    # Also cover in-sample wins predictions.
    train_w, _ = _split_and_impute(WINS_OUTCOME, cols_w, TRAIN_END, TEST_END)
    wins_train_preds = predict(result_w.fit, train_w)
    for i, r in enumerate(train_w.itertuples()):
        d = wins_train_preds[i]
        p05, p50, p95 = (float(np.percentile(d, q)) for q in (5, 50, 95))
        wins_pred_map[f"{int(r.trade_event_id)}:{r.receiver_bref}"] = (
            round(float(d.mean()), 3),
            round(float(d.std()), 3),
            round(p05, 3),
            round(p50, 3),
            round(p95, 3),
            round(float(getattr(r, WINS_OUTCOME)), 3),
        )

    _dollar_transform = OUTCOME in _SIGNED_LOG_OUTCOMES
    for split_df, split_name in ((train_d, "in_sample"), (test_d, "held_out")):
        _preds_raw = predict(result_d.fit, split_df)
        preds = _inv_signed_log(_preds_raw) if _dollar_transform else _preds_raw
        for i, r in enumerate(split_df.itertuples()):
            d = preds[i]
            realized = float(getattr(r, OUTCOME))
            p05, p50, p95 = (float(np.percentile(d, q)) for q in (5, 50, 95))
            # Use median as central tendency for Cauchy-dominated dollar predictions.
            central = float(np.median(d)) if _dollar_transform else float(d.mean())
            key = f"{int(r.trade_event_id)}:{r.receiver_bref}"
            w = wins_pred_map.get(key)
            by_trade[key] = {
                "season": int(r.trade_season),
                "split": split_name,
                # wins fields (headline)
                "wins_mean": w[0] if w else None,
                "wins_sd": w[1] if w else None,
                "wins_p05": w[2] if w else None,
                "wins_p50": w[3] if w else None,
                "wins_p95": w[4] if w else None,
                "wins_realized": w[5] if w else None,
                "wins_realized_in_90ci": bool(w[2] <= w[5] <= w[4]) if w else None,
                # dollar fields (anchor)
                "mean": round(central, 1),
                "sd": round(float(d.std()), 1),
                "p05": round(p05, 1),
                "p50": round(p50, 1),
                "p95": round(p95, 1),
                "realized": round(realized, 1),
                "realized_in_90ci": bool(p05 <= realized <= p95),
                "acquired_players": labels.get((int(r.trade_event_id), r.receiver_bref), []),
                "sender_bref": senders.get((int(r.trade_event_id), r.receiver_bref)),
            }
    logger.info("Built %d per-trade posteriors", len(by_trade))

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "outcome": OUTCOME,
        "wins_outcome": WINS_OUTCOME,
        "unit": "usd",
        "wins_unit": "war",
        "train_window": [2010, TRAIN_END],
        "test_window": [TRAIN_END + 1, TEST_END],
        "scoreboard": {
            "train_n": result_d.train_n,
            "test_n": result_d.test_n,
            "crps": round(result_d.test_crps, 1),
            "coverage_90": round(result_d.coverage_90, 4),
            "mae": round(result_d.test_mae, 1),
            "wins_crps": round(result_w.test_crps, 3),
            "wins_coverage_90": round(result_w.coverage_90, 4),
            "wins_mae": round(result_w.test_mae, 3),
        },
        "comparison": comparison_d,
        "wins_comparison": comparison_w,
        "credible_features": credible_features,
        "cards": cards,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "posteriors.json"
    out.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %d cards → %s", len(cards), out)

    # Per-trade lookup ships in its own file so the /model showcase bundle stays
    # lean — only the Trade Workspace lazy-loads this.
    bt_payload = {
        "generated_at": payload["generated_at"],
        "outcome": OUTCOME,
        "unit": "usd",
        "train_window": [2010, TRAIN_END],
        "test_window": [TRAIN_END + 1, TEST_END],
        "by_trade": by_trade,
    }
    bt_out = OUT_DIR / "by_trade.json"
    # allow_nan=False so a stray non-finite never produces invalid JSON (NaN tokens
    # break strict parsers like Vite's). Cleaned upstream; this is the guardrail.
    bt_out.write_text(json.dumps(bt_payload, separators=(",", ":"), allow_nan=False))
    logger.info("Wrote %d per-trade posteriors → %s", len(by_trade), bt_out)


if __name__ == "__main__":
    main()
