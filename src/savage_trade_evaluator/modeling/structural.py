"""Structural two-part model for captured WAR (R-64).

Target: ``captured_war``, the WAR acquired players earn for the receiving club
from the trade season through T+5, summed per trade side.

Per acquired player: a 3-2-1 weighted WAR rate over the last three completed
seasons, times the seasons the receiving club can expect to hold him inside the
window, split into seasons under team control and seasons after it. Summed per
side, plus the number of players and the number with no MLB time.

The model is two-part: P(side produces non-zero WAR) x a ridge regression on the
non-zero sides, with an empirical, scale-adjusted residual distribution. It is
the production valuation model because it is the one that beats the median and
climatology nulls out-of-sample (``scripts/benchmark_vs_naive.py``).
"""

# pyright: reportCallIssue=false, reportArgumentType=false, reportReturnType=false

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegressionCV, RidgeCV
from sklearn.preprocessing import StandardScaler

from savage_trade_evaluator.modeling.v2.outcomes import build_captured_war
from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

TARGET = "captured_war"
KEYS = ["trade_event_id", "receiver_bref"]
FEATURES: tuple[str, ...] = ("held_ctrl_war", "held_post_war", "n_legs", "n_no_mlb")

# Production fit trains on trades whose T+5 season is complete in bWAR.
TRAIN_START_SEASON = 2010
TRAIN_END_SEASON = 2020
SEASON_DAYS = 183.0
FULL_SEASON_GAMES = 162

_PLAYER_SQL = """
WITH sw AS (
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
              AND year_id = l.trade_year - 1), 0) AS prior_cal_war,
    (SELECT COUNT(*) FROM sw WHERE mlb_id = l.mlb_player_id
     AND year_id < l.first_season) AS n_prior_seasons
FROM structural_legs_in l
"""


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


def player_features(legs: pd.DataFrame, conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Per-player structural features from raw bWAR seasons and the trade date.

    Args:
        legs: One row per acquired player with ``mlb_player_id`` and ``date``.
        conn: Open DuckDB connection.

    Returns:
        ``legs`` plus held_ctrl_war, held_post_war, prior_cal_war, n_legs, n_no_mlb.
    """
    legs = legs.copy()
    when = pd.to_datetime(legs["date"])
    month = when.dt.month.to_numpy()
    legs["trade_year"] = when.dt.year
    # A November or December deal belongs to the season that just ended;
    # first_season is the first season the player can appear for the new club.
    legs["first_season"] = legs["trade_year"] + (month >= 11).astype(int)
    conn.register("structural_legs_in", legs)
    try:
        out = conn.execute(_PLAYER_SQL).df()
    finally:
        conn.unregister("structural_legs_in")

    when = pd.to_datetime(out["date"])
    month = when.dt.month.to_numpy()
    season_end = pd.to_datetime(when.dt.year.astype(str) + "-10-01")
    left = np.clip((season_end - when).dt.days.to_numpy() / SEASON_DAYS, 0.0, 1.0)
    held_ctrl, held_post = held_seasons(month, left, out["n_prior_seasons"].to_numpy())
    rate = (3 * out["w1"] + 2 * out["w2"] + out["w3"]).to_numpy() / 6.0
    out["held_ctrl_war"] = rate * held_ctrl
    out["held_post_war"] = rate * held_post
    out["n_no_mlb"] = (out["n_prior_seasons"] == 0).astype(int)
    out["n_legs"] = 1
    return out


_SIDE_COLS = ["held_ctrl_war", "held_post_war", "prior_cal_war", "n_legs", "n_no_mlb"]


def side_features(start_season: int = TRAIN_START_SEASON, end_season: int = 2024) -> pd.DataFrame:
    """Structural features per historical trade side, keyed on ``KEYS``."""
    with db.connect(read_only=True) as conn:
        legs = conn.execute(
            """
            SELECT trade_event_id, leg_index, to_team_bref AS receiver_bref, trade_season,
                   mlb_player_id, date
            FROM trade_player_unified
            WHERE to_team_bref IS NOT NULL AND trade_season BETWEEN ? AND ?
            """,
            [start_season, end_season],
        ).df()
        feats = player_features(legs, conn)
    return feats.groupby(KEYS, as_index=False)[_SIDE_COLS].sum()


def hypothetical_features(player_mlb_ids: list[int], trade_date: date) -> tuple[pd.DataFrame, str]:
    """One-row structural features for a package of players traded on a date.

    If the season before the player's first season with the new club is still in
    progress in bWAR, the trade is priced as an in-season trade as of the data,
    so a partial season is never read as a full one.

    Args:
        player_mlb_ids: MLBAM ids of the players being acquired.
        trade_date: Date of the hypothetical trade.

    Returns:
        (one-row DataFrame with ``FEATURES``, note describing any date adjustment).
    """
    note = ""
    with db.connect(read_only=True) as conn:
        latest, games = conn.execute(
            "SELECT year_id, MAX(g) FROM bwar_batting "
            "WHERE year_id = (SELECT MAX(year_id) FROM bwar_batting) GROUP BY 1"
        ).fetchone() or (trade_date.year, FULL_SEASON_GAMES)
        played = min(1.0, float(games) / FULL_SEASON_GAMES)
        needs_latest = trade_date.year > latest or (
            trade_date.year == latest and trade_date.month >= 11
        )
        if needs_latest and played < 0.9:
            trade_date = date(int(latest), 4, 1) + timedelta(days=round(played * SEASON_DAYS))
            note = (
                f"bWAR for {latest} is partial ({games} games); "
                f"priced as an in-season trade on {trade_date.isoformat()}"
            )
        legs = pd.DataFrame({"mlb_player_id": player_mlb_ids, "date": pd.Timestamp(trade_date)})
        feats = player_features(legs, conn)
    return feats[_SIDE_COLS].sum().to_frame().T, note


@dataclass(frozen=True)
class StructuralFit:
    """Fitted two-part model.

    Attributes:
        feature_cols: Feature columns, in fit order.
        means: Training means used to impute missing features.
        scaler: Fitted feature scaler.
        clf: Non-zero classifier, or None for a plain regression.
        reg: Ridge regression fitted on the non-zero rows.
        z_pool: Standardized training residuals to resample.
        slope: Residual scale per unit of absolute prediction.
        intercept: Residual scale at a prediction of zero.
        floor: Lower bound on the residual scale.
    """

    feature_cols: tuple[str, ...]
    means: pd.Series
    scaler: StandardScaler
    clf: LogisticRegressionCV | None
    reg: RidgeCV
    z_pool: np.ndarray
    slope: float
    intercept: float
    floor: float


def fit(x: pd.DataFrame, y: np.ndarray, *, hurdle: bool = True) -> StructuralFit:
    """Fit the two-part model.

    Args:
        x: Training features (NaN allowed; imputed with training means).
        y: Training target.
        hurdle: If False, skip the zero/non-zero stage (plain regression).

    Returns:
        A :class:`StructuralFit`.
    """
    x = x.astype("float64")
    means = x.mean().fillna(0.0)
    scaler = StandardScaler().fit(x.fillna(means))
    xs = scaler.transform(x.fillna(means))
    nonzero = y != 0 if hurdle else np.ones(len(y), dtype=bool)
    clf = (
        LogisticRegressionCV(Cs=5, max_iter=2000, scoring="neg_log_loss").fit(xs, nonzero)
        if hurdle
        else None
    )
    reg = RidgeCV(alphas=(1.0, 10.0, 100.0)).fit(xs[nonzero], y[nonzero])
    mu = reg.predict(xs[nonzero])
    resid = y[nonzero] - mu
    # Residual spread grows with the size of the prediction.
    slope, intercept = np.polyfit(np.abs(mu), np.abs(resid), 1)
    floor = float(np.abs(resid).mean()) * 0.25
    scale = np.maximum(intercept + slope * np.abs(mu), floor)
    return StructuralFit(
        feature_cols=tuple(x.columns),
        means=means,
        scaler=scaler,
        clf=clf,
        reg=reg,
        z_pool=resid / scale,
        slope=float(slope),
        intercept=float(intercept),
        floor=floor,
    )


def predict(
    model: StructuralFit, x: pd.DataFrame, rng: np.random.Generator, n_draws: int = 400
) -> tuple[np.ndarray, np.ndarray]:
    """Predictive draws and the analytic expected value.

    Args:
        model: Fitted model.
        x: Features, one row per trade side.
        rng: Random generator for the predictive draws.
        n_draws: Draws per row.

    Returns:
        (draws of shape (n_rows, n_draws), expected value per row). Draw means
        are too noisy to pick a trade side with; use the expected value.
    """
    filled = x.loc[:, list(model.feature_cols)].astype("float64").fillna(model.means)
    xs = model.scaler.transform(filled)
    p_nonzero = model.clf.predict_proba(xs)[:, 1] if model.clf is not None else np.ones(len(x))
    mu = model.reg.predict(xs)
    scale = np.maximum(model.intercept + model.slope * np.abs(mu), model.floor)
    z = rng.choice(model.z_pool, size=(len(x), n_draws))
    draws = mu[:, None] + scale[:, None] * z
    keep = rng.random((len(x), n_draws)) < p_nonzero[:, None]
    expected = p_nonzero * (mu + scale * model.z_pool.mean())
    return np.where(keep, draws, 0.0), expected


@lru_cache(maxsize=1)
def production_fit() -> StructuralFit:
    """Production fit on every trade side with a fully realized T..T+5 window."""
    sides = build_captured_war(TRAIN_START_SEASON, TRAIN_END_SEASON).merge(
        side_features(TRAIN_START_SEASON, TRAIN_END_SEASON), on=KEYS, how="inner"
    )
    # DuckDB row order is not stable; the inner CV splits depend on it.
    sides = sides.sort_values(KEYS).reset_index(drop=True)
    logger.info("structural production fit: n=%d sides", len(sides))
    return fit(sides[list(FEATURES)], sides[TARGET].to_numpy(dtype="float64"))


def score_players(player_mlb_ids: list[int], trade_date: date) -> dict[str, Any]:
    """Captured-WAR forecast for a package of players acquired on a date.

    Args:
        player_mlb_ids: MLBAM ids of the players being acquired.
        trade_date: Date of the hypothetical trade.

    Returns:
        Dict with mean (analytic expected value), median, p5, p95, p_positive,
        the structural ``features`` used, and a ``note`` if the date was adjusted.
    """
    feats, note = hypothetical_features(player_mlb_ids, trade_date)
    draws, expected = predict(production_fit(), feats, np.random.default_rng(137), n_draws=4000)
    row = draws[0]
    return {
        "mean": float(expected[0]),
        "median": float(np.median(row)),
        "p5": float(np.percentile(row, 5)),
        "p95": float(np.percentile(row, 95)),
        "p_positive": float((row > 0).mean()),
        "features": {c: float(feats[c].iloc[0]) for c in FEATURES},
        "train_end_season": TRAIN_END_SEASON,
        "note": note,
    }
