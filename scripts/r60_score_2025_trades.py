"""R-60: Score 2025 trades — forward predictions with posterior uncertainty intervals.

Phase 2 product output. Train V3 on all 2010-2024 realized outcomes, then
generate posterior predictive distributions for 2025 trades whose outcomes
are not yet known (war_delta window T+2..T+5 = 2027-2031; dollar_surplus
T+1..T+3 = 2026-2028).

For each (trade_event, receiving_team) pair we report:
  - mean predicted war_delta (WAR surplus, T+2..T+5)
  - mean predicted dollar_surplus ($M, T+1..T+3)
  - 80% credible interval for each outcome
  - Player names received
  - Whether outcome distribution is clearly positive/negative/uncertain

Imputation: missing 2025 features are filled with training-set means (from
the fit object) so the model sees a consistent distribution. Winsorization to
training ±5σ is applied automatically by predict().
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

logging.basicConfig(
    level=logging.WARNING,  # suppress MCMC noise for product output
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("r60")
logging.getLogger("r60").setLevel(logging.INFO)

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling.v2.features import (
    ALL_FEATURES,
    build_feature_matrix,
)
from savage_trade_evaluator.modeling.v3 import (
    V3_OUTCOME_FEATURES,
    assemble_v3_combined,
    fit_v3,
    predict,
)
from savage_trade_evaluator.storage import db

DOLLAR_SURPLUS_UNIT = 1_000_000  # results are in $M


def load_2025_features() -> pd.DataFrame:
    """Load the 2025 feature matrix (no outcome columns — future trades)."""
    feats = build_feature_matrix(end_season=2025)
    return feats[feats["trade_season"] == 2025].copy().reset_index(drop=True)


def impute_with_training_means(
    df: pd.DataFrame,
    feature_cols: tuple[str, ...],
    training_means: pd.Series,
) -> pd.DataFrame:
    """Fill NaN features with training-set means (from fit object).

    This is the correct imputation strategy for forward scoring:
    we don't have test-set means (there are no outcomes), so we use
    what the model learned from the training distribution.
    """
    df = df.copy()
    for col in feature_cols:
        if col in df.columns:
            fill = float(training_means.get(col, 0.0))
            if np.isnan(fill):
                fill = 0.0
            df[col] = df[col].astype("float64").fillna(fill)
        else:
            df[col] = float(training_means.get(col, 0.0))
    return df


def load_2025_player_names() -> pd.DataFrame:
    """Per (trade_event_id, receiver_bref): comma-joined names of acquired players."""
    with db.connect(read_only=True) as conn:
        rows = conn.execute("""
            SELECT
                trade_event_id,
                to_team_bref AS receiver_bref,
                STRING_AGG(
                    CASE
                        WHEN player_name IS NOT NULL AND player_name != '' THEN player_name
                        WHEN mlb_player_id IS NOT NULL THEN 'P#' || CAST(mlb_player_id AS VARCHAR)
                        ELSE 'PTBNL/Cash'
                    END,
                    ', ' ORDER BY player_name NULLS LAST
                ) AS players_received,
                STRING_AGG(DISTINCT from_team_bref, '/') AS from_teams
            FROM trade_player_unified
            WHERE trade_season = 2025
              AND to_team_bref IS NOT NULL
              AND from_team_bref IS NOT NULL
              AND from_team_bref != to_team_bref
            GROUP BY trade_event_id, to_team_bref
        """).df()
    return rows


def score_outcome(
    outcome: str,
    combined: pd.DataFrame,
    features_2025: pd.DataFrame,
) -> pd.DataFrame:
    """Train on 2010-2024, predict posterior for 2025 trades.

    Returns DataFrame with (trade_event_id, receiver_bref, mean, p10, p90, p50).
    """
    feature_cols = V3_OUTCOME_FEATURES[outcome]

    # Train on full 2010-2024 history
    logger.info("Fitting %s on %d training rows...", outcome, len(combined))
    train = combined[combined[outcome].notna()].copy()
    for col in feature_cols:
        fill = float(train[col].mean()) if col in train.columns else 0.0
        if np.isnan(fill):
            fill = 0.0
        train[col] = train[col].astype("float64").fillna(fill)

    fit = fit_v3(train, outcome, feature_cols)

    # Impute 2025 features with training means
    test = impute_with_training_means(features_2025, feature_cols, fit.feature_means)

    # Generate posterior predictive samples
    preds = predict(fit, test)  # (n_test, n_samples)

    # Summarize
    mean_ = preds.mean(axis=1)
    p10 = np.percentile(preds, 10, axis=1)
    p25 = np.percentile(preds, 25, axis=1)
    p50 = np.percentile(preds, 50, axis=1)
    p75 = np.percentile(preds, 75, axis=1)
    p90 = np.percentile(preds, 90, axis=1)

    result = features_2025[["trade_event_id", "receiver_bref"]].copy()
    result[f"{outcome}_mean"] = mean_
    result[f"{outcome}_p10"] = p10
    result[f"{outcome}_p25"] = p25
    result[f"{outcome}_p50"] = p50
    result[f"{outcome}_p75"] = p75
    result[f"{outcome}_p90"] = p90

    return result


def verdict(mean: float, p10: float, p90: float, unit: str) -> str:
    """One-word directional verdict based on credible interval."""
    if p10 > 0:
        return f"CLEAR WIN  (+{mean:.1f}{unit})"
    elif p90 < 0:
        return f"CLEAR LOSS ({mean:.1f}{unit})"
    elif mean > 0:
        return f"lean +     ({mean:+.1f}{unit})"
    else:
        return f"lean -     ({mean:+.1f}{unit})"


def print_scoreboard(merged: pd.DataFrame, top_n: int = 30) -> None:
    """Print ranked trade scoreboard sorted by predicted dollar_surplus."""
    sep = "=" * 120
    print()
    print(sep)
    print("R-60: 2025 MLB TRADE PREDICTIONS — POSTERIOR DISTRIBUTIONS")
    print("Trained on 2010-2024 realized outcomes. Outcomes not yet known.")
    print("war_delta = WAR surplus T+2..T+5 (2027-2031).  dollar_surplus = $/WAR surplus T+1..T+3 (2026-2028).")
    print("80% CI = [p10, p90].  Verdict: CLEAR if 80% CI excludes zero.")
    print(sep)

    df = merged.copy()
    df = df.sort_values("dollar_surplus_mean", ascending=False)

    print()
    print(f"{'Rank':<4} {'Event':>9} {'Team':>4}  {'Players Received':<40}  "
          f"{'$surplus':>10} {'[p10':>8} {'p90]':>8}  "
          f"{'war_delta':>10} {'[p10':>7} {'p90]':>7}  Verdict")
    print("-" * 120)

    for rank, (_, row) in enumerate(df.iterrows(), 1):
        if rank > top_n:
            break
        players = str(row.get("players_received", ""))[:38]
        ds_mean = row["dollar_surplus_mean"] / DOLLAR_SURPLUS_UNIT
        ds_p10 = row["dollar_surplus_p10"] / DOLLAR_SURPLUS_UNIT
        ds_p90 = row["dollar_surplus_p90"] / DOLLAR_SURPLUS_UNIT
        wd_mean = row["war_delta_mean"]
        wd_p10 = row["war_delta_p10"]
        wd_p90 = row["war_delta_p90"]
        verd = verdict(ds_mean, ds_p10, ds_p90, "M")
        print(
            f"{rank:<4} {int(row['trade_event_id']):>9} {row['receiver_bref']:>4}  "
            f"{players:<40}  "
            f"{ds_mean:>+9.1f}M {ds_p10:>+7.1f}M {ds_p90:>+7.1f}M  "
            f"{wd_mean:>+9.2f}W {wd_p10:>+6.2f}W {wd_p90:>+6.2f}W  {verd}"
        )

    print()
    # Summary stats
    clear_wins = (merged["dollar_surplus_p10"] > 0).sum()
    clear_losses = (merged["dollar_surplus_p90"] < 0).sum()
    uncertain = len(merged) - clear_wins - clear_losses
    print(f"  {len(merged)} trade-sides scored.  "
          f"Clear wins: {clear_wins}  Clear losses: {clear_losses}  Uncertain: {uncertain}")
    print(f"  Median predicted dollar_surplus: "
          f"{merged['dollar_surplus_mean'].median()/DOLLAR_SURPLUS_UNIT:+.1f}M")
    print(f"  Median predicted war_delta: {merged['war_delta_mean'].median():+.2f} WAR")
    print(sep)


def main() -> None:
    logger.info("Loading 2025 feature matrix...")
    features_2025 = load_2025_features()
    logger.info("2025 feature rows: %d", len(features_2025))

    logger.info("Loading training data (2010-2024)...")
    combined = assemble_v3_combined()
    logger.info("Training rows: %d", len(combined))

    logger.info("Fitting war_delta model...")
    war_scores = score_outcome("war_delta", combined, features_2025)

    logger.info("Fitting dollar_surplus model...")
    dollar_scores = score_outcome("dollar_surplus", combined, features_2025)

    logger.info("Loading 2025 player names...")
    player_names = load_2025_player_names()

    # Merge all
    merged = (
        features_2025[["trade_event_id", "receiver_bref"]]
        .merge(war_scores, on=["trade_event_id", "receiver_bref"], how="left")
        .merge(dollar_scores, on=["trade_event_id", "receiver_bref"], how="left")
        .merge(player_names, on=["trade_event_id", "receiver_bref"], how="left")
    )

    print_scoreboard(merged, top_n=40)


if __name__ == "__main__":
    main()
