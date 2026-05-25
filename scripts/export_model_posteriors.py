"""Export real V3 posteriors to JSON for the frontend.

This is the **first model-backed export** — every other ``export_*.py`` script
ships the pre-model heuristic layer (documented in ``export_warroom.py``). This
one fits the frozen V3 ``dollar_surplus`` model on the 2010-2020 training window,
predicts on the held-out 2021-2024 trades, and writes the real posterior-predictive
distribution for a curated set of recognizable deadline trades.

Because the featured trades are *held-out* (post-2020), we also know the realized
``dollar_surplus`` outcome — so each card shows the model's predicted distribution
against the truth, plus whether the 90% credible interval covered it. That's the
honest scoreboard: a distribution, a realized value, and a coverage check.

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

from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
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
from r58_baseline_comparison import run_fold_comparison  # noqa: E402

logger = logging.getLogger(__name__)

OUTCOME = "dollar_surplus"
TRAIN_END = 2020
TEST_END = 2024
OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "data" / "model"

# Curated held-out trades to feature, each tagged with its narrative role:
#   "covered"   — realized outcome fell inside the 90% credible interval
#   "tail_miss" — a known limitation: the model shrinks extreme-tail blockbusters
#                 toward the regime mean (CLAUDE.md validation philosophy). Shown
#                 deliberately so the demo is honest about where V3 fails.
FEATURED: tuple[tuple[int, str, str], ...] = (
    (808316, "CHC", "covered"),    # Kyle Tucker → Cubs, 2024 (headline)
    (768021, "SDP", "covered"),    # Luis Arraez → Padres, 2024
    (739097, "BAL", "covered"),    # Corbin Burnes → Orioles, 2024
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
            WHERE trade_season BETWEEN 2021 AND 2024
            """,
        ).df()
    labels: dict[tuple[int, str], list[str]] = {}
    senders: dict[tuple[int, str], str] = {}
    for r in rows.itertuples():
        key = (int(r.trade_event_id), r.receiver_bref)
        labels.setdefault(key, [])
        if r.player_name and r.player_name not in labels[key]:
            labels[key].append(r.player_name)
        if r.sender_bref:
            senders[key] = r.sender_bref
    _player_labels._senders = senders  # type: ignore[attr-defined]
    return labels


def _walk_forward_comparison() -> dict[str, object]:
    """Validated walk-forward CV comparison (R-58 methodology, D-39/D-41 numbers).

    Per 2-year fold, scores three models by CRPS (lower is better):
      * context-aware    — full V3 model (ALL_FEATURES, receiving-team context)
      * player-quality    — single feature (receiver_acquired_player_quality)
      * intercept-only    — Bayesian "predict the mean" floor

    Returns per-fold rows plus aggregate skill, computed two honest ways:
    vs player-quality (the thesis win) and vs intercept-only (parity on raw $).
    The structural-break fold (2017-18) is flagged, not hidden.
    """
    combined = assemble_v3_combined()
    feature_cols = V3_OUTCOME_FEATURES[OUTCOME]
    min_n = MIN_TEST_N.get(OUTCOME, 50)
    splits = walk_forward_splits(OUTCOME, combined)

    folds = []
    for sp in splits:
        r = run_fold_comparison(
            OUTCOME, feature_cols, combined=combined,
            train_end=sp.train_end, test_end=sp.test_end,
            train_start=sp.train_start, min_n=min_n,
        )
        # The 2017-18 fold is the documented structural break (D-40).
        is_break = sp.test_start <= 2017 <= sp.test_end
        folds.append({
            "label": f"{sp.test_start}–{sp.test_end}",
            "n_test": int(r["n_test"]),
            "crps_context": round(float(r["crps_model"]), 1),
            "crps_quality": round(float(r["crps_quality"]), 1),
            "crps_intercept": round(float(r["crps_intercept"]), 1),
            "skill_vs_quality": round(float(r["skill_model_vs_quality"]), 4),
            "skill_vs_intercept": round(float(r["skill_vs_bayes_intercept"]), 4),
            "structural_break": is_break,
        })

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


def _summarize(draws: np.ndarray) -> dict[str, object]:
    """Posterior summary for a single trade's predictive draws (1D array)."""
    rng = np.random.default_rng(137)
    embed = draws if draws.size <= N_DRAWS_EMBED else rng.choice(draws, N_DRAWS_EMBED, replace=False)
    return {
        "mean": float(draws.mean()),
        "sd": float(draws.std()),
        "p05": float(np.percentile(draws, 5)),
        "p25": float(np.percentile(draws, 25)),
        "p50": float(np.percentile(draws, 50)),
        "p75": float(np.percentile(draws, 75)),
        "p95": float(np.percentile(draws, 95)),
        "draws": [round(float(x), 1) for x in sorted(embed)],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cols = V3_OUTCOME_FEATURES[OUTCOME]

    logger.info("Fitting V3 %s on %d-%d, scoring %d-%d ...", OUTCOME, 2010, TRAIN_END, TRAIN_END + 1, TEST_END)
    result = backtest_outcome_v3(OUTCOME, train_end_season=TRAIN_END, test_end_season=TEST_END)
    logger.info(
        "  train_n=%d test_n=%d  CRPS=%.0f  coverage_90=%.2f",
        result.train_n, result.test_n, result.test_crps, result.coverage_90,
    )

    # Re-derive the test split so we can predict full draws for featured trades.
    _, test = _split_and_impute(OUTCOME, cols, TRAIN_END, TEST_END)

    logger.info("Running walk-forward baseline comparison (R-58 methodology) ...")
    comparison = _walk_forward_comparison()
    for f in comparison["folds"]:
        flag = "  [structural break]" if f["structural_break"] else ""
        logger.info(
            "  fold %s  n=%d  vs_quality=%+.1f%%  vs_intercept=%+.1f%%%s",
            f["label"], f["n_test"],
            f["skill_vs_quality"] * 100, f["skill_vs_intercept"] * 100, flag,
        )
    logger.info(
        "  mean skill vs quality=%+.1f%% (ex-break %+.1f%%) · vs intercept=%+.1f%% (ex-break %+.1f%%)",
        comparison["mean_skill_vs_quality"] * 100, comparison["mean_skill_vs_quality_ex_break"] * 100,
        comparison["mean_skill_vs_intercept"] * 100, comparison["mean_skill_vs_intercept_ex_break"] * 100,
    )

    labels = _player_labels()
    senders: dict[tuple[int, str], str] = _player_labels._senders  # type: ignore[attr-defined]

    cred = result.credible_features
    credible = cred[cred["credible"]].head(8)
    credible_features = [
        {
            "feature": r.feature,
            "beta": round(float(r.mean_beta), 4),
            "directional_mass": round(float(r.directional_mass), 3),
        }
        for r in credible.itertuples()
    ]

    cards = []
    for event_id, recv, role in FEATURED:
        mask = (test["trade_event_id"] == event_id) & (test["receiver_bref"] == recv)
        if not mask.any():
            logger.warning("  SKIP %s/%s — not in held-out test split", event_id, recv)
            continue
        row = test[mask]
        draws = predict(result.fit, row)[0]  # (n_samples,)
        realized = float(row[OUTCOME].iloc[0])
        summary = _summarize(draws)
        in_ci = summary["p05"] <= realized <= summary["p95"]
        cards.append({
            "trade_event_id": int(event_id),
            "receiver_bref": recv,
            "sender_bref": senders.get((event_id, recv)),
            "season": int(row["trade_season"].iloc[0]),
            "role": role,
            "acquired_players": labels.get((event_id, recv), []),
            "posterior": summary,
            "realized": round(realized, 1),
            "realized_in_90ci": bool(in_ci),
        })
        logger.info(
            "  %s/%s  pred=$%.1fM [%.1f, %.1f]  realized=$%.1fM  in90CI=%s",
            event_id, recv,
            summary["mean"] / 1e6, summary["p05"] / 1e6, summary["p95"] / 1e6,
            realized / 1e6, in_ci,
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "outcome": OUTCOME,
        "unit": "usd",
        "train_window": [2010, TRAIN_END],
        "test_window": [TRAIN_END + 1, TEST_END],
        "scoreboard": {
            "train_n": result.train_n,
            "test_n": result.test_n,
            "crps": round(result.test_crps, 1),
            "coverage_90": round(result.coverage_90, 4),
            "mae": round(result.test_mae, 1),
        },
        "comparison": comparison,
        "credible_features": credible_features,
        "cards": cards,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "posteriors.json"
    out.write_text(json.dumps(payload, indent=2))
    logger.info("Wrote %d cards → %s", len(cards), out)


if __name__ == "__main__":
    main()
