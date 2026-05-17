"""V2 context-aware predictive model — linear least-squares first pass.

The naïve baseline (``naive_baseline.py``) computes *realized* surplus from
post-trade WAR data. This module fits a *predictive* model: given pre-trade
team-season features, predict the realized surplus.

V0 implementation: ordinary least-squares regression on a small set of team
context features. This is **deliberately simple** — proves the architecture
(feature extraction → fit → predict → score) without committing to Stan or
brms yet. The Phase 2.5 deliverable swaps OLS for a multilevel Bayesian fit
without changing the surrounding code (same train/predict/score interface).

Train-test split is out-of-time per D-10: train on trades <=2020, test on
2021-2024. Scoring metric is MAE on predicted vs realized surplus.

Caveats vs the full Phase 2 plan:

* No selection-on-gains correction (Mixtape Ch 4 ATT vs ATE).
* No playoff-probability or payroll-room features (needs standings adapter).
* No prospect-specific features (needs FG prospect data, currently blocked).
* No posterior distribution (point estimates only — D-13 wants distributions;
  swap to Bayesian in 2.5).
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from savage_trade_evaluator.storage import db

FEATURE_COLUMNS: tuple[str, ...] = (
    "receiver_prior_year_war",
    "receiver_dev_fit_pitching",
    "receiver_dev_fit_hitting",
    "receiver_prior_year_wins",
    "receiver_prior_year_pyth_pct",
    "receiver_org_pitcher_k_jump_3yr",
    "receiver_org_hitter_xwoba_jump_3yr",
    "receiver_coach_hitter_xwoba_jump_3yr",
    "receiver_best_draft_pick",
    "receiver_acquired_from_dev_cluster_score",
    "receiver_acquired_player_quality",
)


@dataclass(frozen=True, slots=True)
class FitResult:
    """Output of fitting the context-aware OLS model."""

    feature_columns: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    train_mae: float
    test_mae: float
    naive_zero_mae_test: float
    n_train: int
    n_test: int


def _load_context_dataset() -> pd.DataFrame:
    """Pull (surplus, features) per (trade_event, receiving-team) for training/eval."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT trade_event_id, trade_season, receiver_bref, surplus,
                   {", ".join(FEATURE_COLUMNS)}
            FROM trade_with_context
            WHERE surplus IS NOT NULL
              AND {" AND ".join(f"{c} IS NOT NULL" for c in FEATURE_COLUMNS)}
            """
        ).df()
    return df


def fit(test_start_season: int = 2021) -> FitResult:
    """Fit OLS on pre-``test_start_season`` data and evaluate on the rest.

    Args:
        test_start_season: Trades from this year onward become the test set
            (default 2021, per D-10 leaning).

    Returns:
        ``FitResult`` carrying coefficients + intercept + train/test MAE +
        the naive "predict 0" benchmark MAE on the same test set.
    """
    df = _load_context_dataset()
    if df.empty:
        raise RuntimeError(
            "no rows in trade_with_context — run `ste backtest naive` and `ste features` first"
        )

    train_df = df[df.trade_season < test_start_season]
    test_df = df[df.trade_season >= test_start_season]

    x_train = train_df[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
    y_train = train_df["surplus"].to_numpy(dtype=float)
    x_test = test_df[list(FEATURE_COLUMNS)].to_numpy(dtype=float)
    y_test = test_df["surplus"].to_numpy(dtype=float)

    # Solve OLS with an intercept column.
    x_train_aug = np.hstack([np.ones((x_train.shape[0], 1)), x_train])
    coefs_with_intercept, *_ = np.linalg.lstsq(x_train_aug, y_train, rcond=None)
    intercept = float(coefs_with_intercept[0])
    coefs = tuple(float(c) for c in coefs_with_intercept[1:])

    def predict(x: np.ndarray) -> np.ndarray:
        return intercept + x @ np.array(coefs)

    train_mae = float(np.mean(np.abs(predict(x_train) - y_train)))
    test_mae = float(np.mean(np.abs(predict(x_test) - y_test)))
    naive_zero_mae_test = float(np.mean(np.abs(y_test)))

    return FitResult(
        feature_columns=FEATURE_COLUMNS,
        coefficients=coefs,
        intercept=intercept,
        train_mae=train_mae,
        test_mae=test_mae,
        naive_zero_mae_test=naive_zero_mae_test,
        n_train=int(x_train.shape[0]),
        n_test=int(x_test.shape[0]),
    )
