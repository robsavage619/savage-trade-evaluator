"""R-64: rebuild the trade-outcome model from the prior-WAR heuristic upward.

Target: captured_war (WAR earned for the receiving club, T..T+5, per trade side).

The structural features and the two-part model live in
``savage_trade_evaluator.modeling.structural``; this script is the experiment
that chose them.

Protocol: specs are compared on pre-2018 walk-forward folds only. The spec with
the best pooled fold CRPS is then scored once on the 2018-2021 holdout.

Run:
  uv run python scripts/r64_baseline_up.py
"""

# pyright: reportCallIssue=false, reportArgumentType=false, reportReturnType=false

from __future__ import annotations

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling import structural
from savage_trade_evaluator.modeling.metrics import crps_empirical
from savage_trade_evaluator.modeling.v3 import V3_OUTCOME_FEATURES, assemble_v3_combined

TARGET = "captured_war"
KEYS = ["trade_event_id", "receiver_bref"]
HOLDOUT_START, HOLDOUT_END = 2018, 2021
CV_TEST_SEASONS = (2014, 2015, 2016, 2017)
N_DRAWS = 400

STRUCTURAL = structural.FEATURES
NAIVE = ("prior_cal_war", "n_legs")


def margins(frame: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Side-A-minus-side-B margins for trades with exactly two sides in ``frame``."""
    two = frame[frame.groupby("trade_event_id")["receiver_bref"].transform("count") == 2]
    two = two.sort_values(KEYS)
    grouped = two.groupby("trade_event_id")[cols]
    return (grouped.first() - grouped.last()).to_numpy(dtype="float64")


def decision(frame: pd.DataFrame, col: str) -> dict[str, float]:
    """Favoured-side win rate and WAR gained per trade, with a 95% half-width."""
    m = margins(frame, [col, TARGET])
    decisive = (np.abs(m[:, 0]) > 1e-9) & (np.abs(m[:, 1]) > 1e-9)
    gained = np.sign(m[decisive, 0]) * m[decisive, 1]
    return {
        "Win%": float(np.mean(gained > 0)),
        "WAR/trade": float(gained.mean()),
        "+/-": float(1.96 * gained.std(ddof=1) / np.sqrt(len(gained))),
        "n_trades": len(gained),
    }


def score(test: pd.DataFrame, draws: np.ndarray, expected: np.ndarray) -> dict[str, float]:
    """MAE (predictive median), CRPS, 90% coverage and the decision-level score."""
    y = test[TARGET].to_numpy(dtype="float64")
    lo, hi = np.percentile(draws, [5, 95], axis=1)
    return {
        "MAE": float(np.abs(y - np.median(draws, axis=1)).mean()),
        "CRPS": crps_empirical(y, draws),
        "Cov90": float(np.mean((y >= lo) & (y <= hi))),
        **decision(test[[*KEYS, TARGET]].assign(pred=expected), "pred"),
    }


def null_rows(train: pd.DataFrame, test: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Median and climatology nulls, plus two unfitted pick-the-side heuristics."""
    y_train = np.sort(train[TARGET].to_numpy(dtype="float64"))
    y = test[TARGET].to_numpy(dtype="float64")
    out: dict[str, dict[str, float]] = {
        "null: median / climatology": {
            "MAE": float(np.abs(y - np.median(y_train)).mean()),
            "CRPS": crps_empirical(y, np.tile(y_train, (len(y), 1))),
        }
    }
    held = test.assign(held=test["held_ctrl_war"] + test["held_post_war"])
    for label, col in (("pick: more T-1 WAR", "prior_cal_war"), ("pick: more held WAR", "held")):
        out[label] = decision(held, col)
    return out


def main() -> None:
    context = tuple(V3_OUTCOME_FEATURES[TARGET])
    specs: dict[str, tuple[tuple[str, ...], bool]] = {
        "A  T-1 WAR, plain regression": (NAIVE, False),
        "B  T-1 WAR, two-part": (NAIVE, True),
        "C  structural, two-part": (STRUCTURAL, True),
        "D  34 context features, two-part": (context, True),
        "E  structural + 34 context, two-part": (STRUCTURAL + context, True),
    }
    df = assemble_v3_combined().dropna(subset=[TARGET])
    df = df[df["trade_season"] <= HOLDOUT_END].merge(
        structural.side_features(2010, HOLDOUT_END), on=KEYS, how="left"
    )
    # DuckDB row order is not stable; the inner CV splits depend on it.
    df = df.sort_values(KEYS).reset_index(drop=True)
    dev = df[df["trade_season"] < HOLDOUT_START]

    def run(
        train: pd.DataFrame, test: pd.DataFrame, cols: tuple[str, ...], hurdle: bool
    ) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(137)
        y_train = train[TARGET].to_numpy(dtype="float64")
        model = structural.fit(train[list(cols)], y_train, hurdle=hurdle)
        return structural.predict(model, test[list(cols)], rng, N_DRAWS)

    # ── Walk-forward on the development seasons only ──────────────────────────
    folds = [(dev[dev["trade_season"] < s], dev[dev["trade_season"] == s]) for s in CV_TEST_SEASONS]
    pooled_test = pd.concat([test for _, test in folds])
    cv: dict[str, dict[str, float]] = {}
    for label, (cols, hurdle) in specs.items():
        parts = [run(train, test, cols, hurdle) for train, test in folds]
        draws = np.vstack([d for d, _ in parts])
        cv[label] = score(pooled_test, draws, np.concatenate([e for _, e in parts]))
    null_cv = [null_rows(train, test) for train, test in folds]
    weights = np.array([len(test) for _, test in folds], dtype="float64")
    for key in ("MAE", "CRPS"):
        vals = np.array([n["null: median / climatology"][key] for n in null_cv])
        cv.setdefault("null: median / climatology", {})[key] = float(vals @ weights / weights.sum())
    cv.update(
        {
            k: v
            for k, v in null_rows(dev[dev["trade_season"] < 2014], pooled_test).items()
            if k.startswith("pick")
        }
    )
    print(f"WALK-FORWARD, test seasons {CV_TEST_SEASONS}, n={len(pooled_test)} sides")
    print(pd.DataFrame(cv).T.round(3).fillna("").to_string())

    # ── One holdout score for the walk-forward winner ─────────────────────────
    best = min(specs, key=lambda k: cv[k]["CRPS"])
    holdout = df[df["trade_season"] >= HOLDOUT_START]
    cols, hurdle = specs[best]
    result = {best: score(holdout, *run(dev, holdout, cols, hurdle)), **null_rows(dev, holdout)}
    print(
        f"\nHOLDOUT {HOLDOUT_START}-{HOLDOUT_END}, n={len(holdout)} sides, chosen on fold CRPS: {best}"
    )
    print(pd.DataFrame(result).T.round(3).fillna("").to_string())


if __name__ == "__main__":
    main()
