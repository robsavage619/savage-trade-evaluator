"""R-64: rebuild the trade-outcome model from the prior-WAR heuristic upward.

Target: captured_war (WAR earned for the receiving club, T..T+5, per trade side).

Structural baseline, per acquired player: a 3-2-1 weighted WAR rate over the last
three completed seasons, times the seasons the receiving club can expect to hold
him inside the target window, split into seasons under team control and seasons
after it. Summed per side.

Every spec is a two-part model: P(side produces non-zero WAR) x a ridge regression
on the non-zero sides, with an empirical, scale-adjusted residual distribution.

Protocol: specs are compared on pre-2018 walk-forward folds only. The spec with
the best pooled fold CRPS is then scored once on the 2018-2021 holdout.

Run:
  uv run python scripts/r64_baseline_up.py
"""

# pyright: reportCallIssue=false, reportArgumentType=false, reportReturnType=false

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegressionCV, RidgeCV
from sklearn.preprocessing import StandardScaler

from savage_trade_evaluator.modeling.metrics import crps_empirical
from savage_trade_evaluator.modeling.v3 import V3_OUTCOME_FEATURES, assemble_v3_combined
from savage_trade_evaluator.storage import db

TARGET = "captured_war"
KEYS = ["trade_event_id", "receiver_bref"]
HOLDOUT_START, HOLDOUT_END = 2018, 2021
CV_TEST_SEASONS = (2014, 2015, 2016, 2017)
N_DRAWS = 400

# trade_season is the calendar year of the trade, so a November or December deal
# belongs to the season that just ended. first_season is the first season the
# player can appear for the receiving club.
_LEGS_SQL = f"""
WITH legs AS (
    SELECT trade_event_id, leg_index, to_team_bref AS receiver_bref, trade_season,
           mlb_player_id, date,
           CASE WHEN month(date) >= 11 THEN trade_season + 1 ELSE trade_season END
               AS first_season
    FROM trade_player_unified
    WHERE to_team_bref IS NOT NULL AND trade_season BETWEEN 2010 AND {HOLDOUT_END}
),
sw AS (
    SELECT mlb_id, year_id, SUM(war) AS war
    FROM bwar_player_seasons WHERE mlb_id IS NOT NULL GROUP BY 1, 2
)
SELECT l.*,
    COALESCE((SELECT war FROM sw WHERE mlb_id = l.mlb_player_id
              AND year_id = l.first_season - 1), 0) AS w1,
    COALESCE((SELECT war FROM sw WHERE mlb_id = l.mlb_player_id
              AND year_id = l.first_season - 2), 0) AS w2,
    COALESCE((SELECT war FROM sw WHERE mlb_id = l.mlb_player_id
              AND year_id = l.first_season - 3), 0) AS w3,
    COALESCE((SELECT war FROM sw WHERE mlb_id = l.mlb_player_id
              AND year_id = l.trade_season - 1), 0) AS prior_cal_war,
    (SELECT COUNT(*) FROM sw WHERE mlb_id = l.mlb_player_id
     AND year_id < l.first_season) AS n_prior_seasons
FROM legs l
"""

STRUCTURAL = ("held_ctrl_war", "held_post_war", "n_legs", "n_no_mlb")
NAIVE = ("prior_cal_war", "n_legs")


def held_seasons(
    month: np.ndarray, season_left: np.ndarray, n_prior_seasons: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Full-season equivalents inside the T..T+5 window, split by team control.

    The window is whatever is left of the trade season plus five full seasons.
    Control is six MLB seasons, counted from the first season the player can
    appear for the receiving club.

    Args:
        month: Calendar month of the trade.
        season_left: Share of the trade season remaining (used April to October).
        n_prior_seasons: MLB seasons completed before that first season.

    Returns:
        (seasons held under control, seasons held after control ends).
    """
    first_weight = np.where(month <= 3, 1.0, np.where(month >= 11, 0.0, season_left))
    control = np.clip(6 - n_prior_seasons, 0, 6)
    # The trade season counts against control only if it is actually played.
    ctrl_after = np.clip(control - (month <= 10).astype(int), 0, 5)
    held_ctrl = np.where(control > 0, first_weight, 0.0) + ctrl_after
    held_post = np.where(control > 0, 0.0, first_weight) + (5 - ctrl_after)
    return held_ctrl, held_post


def _self_check() -> None:
    month, left, prior = np.array([7, 12, 2]), np.array([0.4, 0.0, 1.0]), np.array([5, 0, 6])
    ctrl, post = held_seasons(month, left, prior)
    # July, last control year / December, rookie / February, free-agent-eligible veteran
    assert np.allclose(ctrl, [0.4, 5.0, 0.0]), ctrl
    assert np.allclose(post, [5.0, 0.0, 6.0]), post


def side_features() -> pd.DataFrame:
    """Per-side structural features built from raw bWAR seasons and trade dates."""
    with db.connect(read_only=True) as conn:
        legs = conn.execute(_LEGS_SQL).df()
    date = pd.to_datetime(legs["date"])
    month = date.dt.month.to_numpy()
    season_end = pd.to_datetime(date.dt.year.astype(str) + "-10-01")
    left = np.clip((season_end - date).dt.days.to_numpy() / 183.0, 0.0, 1.0)
    held_ctrl, held_post = held_seasons(month, left, legs["n_prior_seasons"].to_numpy())
    rate = (3 * legs["w1"] + 2 * legs["w2"] + legs["w3"]).to_numpy() / 6.0
    legs["held_ctrl_war"] = rate * held_ctrl
    legs["held_post_war"] = rate * held_post
    legs["n_no_mlb"] = (legs["n_prior_seasons"] == 0).astype(int)
    legs["n_legs"] = 1
    cols = ["held_ctrl_war", "held_post_war", "prior_cal_war", "n_legs", "n_no_mlb"]
    return legs.groupby(KEYS, as_index=False)[cols].sum()


def predict_samples(
    x_train: pd.DataFrame,
    y_train: np.ndarray,
    x_test: pd.DataFrame,
    rng: np.random.Generator,
    *,
    hurdle: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Two-part predictive draws, shape (n_test, N_DRAWS), and the expected value.

    Args:
        x_train: Training features (NaN allowed; imputed with training means).
        y_train: Training target.
        x_test: Test features.
        rng: Random generator for the predictive draws.
        hurdle: If False, skip the zero/non-zero stage (plain regression).

    Returns:
        Predictive draws per test row, and the analytic expected value per row
        (draw means are too noisy to pick a trade side with).
    """
    means = x_train.mean().fillna(0.0)
    scaler = StandardScaler().fit(x_train.fillna(means))
    xs_train = scaler.transform(x_train.fillna(means))
    xs_test = scaler.transform(x_test.fillna(means))

    nonzero = y_train != 0 if hurdle else np.ones(len(y_train), dtype=bool)
    if hurdle:
        clf = LogisticRegressionCV(Cs=5, max_iter=2000).fit(xs_train, nonzero)
        p_nonzero = clf.predict_proba(xs_test)[:, 1]
    else:
        p_nonzero = np.ones(len(x_test))

    reg = RidgeCV(alphas=(1.0, 10.0, 100.0)).fit(xs_train[nonzero], y_train[nonzero])
    mu_train, mu_test = reg.predict(xs_train[nonzero]), reg.predict(xs_test)
    resid = y_train[nonzero] - mu_train
    # Residual spread grows with the size of the prediction.
    slope, intercept = np.polyfit(np.abs(mu_train), np.abs(resid), 1)
    floor = float(np.abs(resid).mean()) * 0.25
    scale_train = np.maximum(intercept + slope * np.abs(mu_train), floor)
    scale_test = np.maximum(intercept + slope * np.abs(mu_test), floor)
    z_pool = resid / scale_train
    z = rng.choice(z_pool, size=(len(x_test), N_DRAWS))
    draws = mu_test[:, None] + scale_test[:, None] * z
    keep = rng.random((len(x_test), N_DRAWS)) < p_nonzero[:, None]
    expected = p_nonzero * (mu_test + scale_test * z_pool.mean())
    return np.where(keep, draws, 0.0), expected


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
    _self_check()
    context = tuple(V3_OUTCOME_FEATURES[TARGET])
    specs: dict[str, tuple[tuple[str, ...], bool]] = {
        "A  T-1 WAR, plain regression": (NAIVE, False),
        "B  T-1 WAR, two-part": (NAIVE, True),
        "C  structural, two-part": (STRUCTURAL, True),
        "D  34 context features, two-part": (context, True),
        "E  structural + 34 context, two-part": (STRUCTURAL + context, True),
    }
    df = assemble_v3_combined().dropna(subset=[TARGET])
    df = df[df["trade_season"] <= HOLDOUT_END].merge(side_features(), on=KEYS, how="left")
    # DuckDB row order is not stable; the inner CV splits depend on it.
    df = df.sort_values(KEYS).reset_index(drop=True)
    dev = df[df["trade_season"] < HOLDOUT_START]

    def run(
        train: pd.DataFrame, test: pd.DataFrame, cols: tuple[str, ...], hurdle: bool
    ) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(137)
        y_train = train[TARGET].to_numpy(dtype="float64")
        x_train = train[list(cols)].astype("float64")
        x_test = test[list(cols)].astype("float64")
        return predict_samples(x_train, y_train, x_test, rng, hurdle=hurdle)

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
