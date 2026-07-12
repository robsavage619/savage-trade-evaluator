"""GM trade acceptance model.

Estimates P(accept | GM profile, package shape) using a logistic regression
trained on weak-labeled trade rumors from MLBTR.

Labeling logic:
  positive (accepted=1): a transaction in ``transactions`` matches a rumored
    player + team pair within 90 days of the MLBTR post date.
  negative (accepted=0): a trade_rumor post where no matching transaction is
    found within 90 days — assumed the GM rejected or the deal fell apart.

This is a weak-label setup. The negatives are noisy (some rumors are
misreported; some deals take longer). The model is intentionally simple —
it feeds into cycle ranking as a prior, not a hard gate.

Features (from gm_behavioral_profiles for the *receiving* GM):
  war_buyer_bias    — WAR-acquisition tendency (continuous)
  avg_age_received  — preferred player age (continuous)
  deadline_pct      — deadline concentration (continuous)
  archetype_id      — cluster_id from gm_archetypes (one-hot encoded)

Package shape feature (from transaction or rumor context):
  n_players_package — number of players moving in the rumored deal
    (approximated as 1 for all rumors in v1 — most MLBTR posts are single-player)

Model: sklearn LogisticRegression with L2 penalty, standard-scaled features.
Fit is stored in memory; call ``fit()`` to train and ``predict_proba()`` to score.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

_NUMERIC_FEATURES = [
    "war_buyer_bias",
    "avg_age_received",
    "deadline_pct",
]
_CATEGORICAL_FEATURES = ["cluster_id"]

# Days window for matching a rumor to a transaction
_MATCH_WINDOW_DAYS = 90


@dataclass
class AcceptanceModel:
    """Fitted GM acceptance logistic model.

    Attributes:
        pipeline: Fitted sklearn pipeline (ColumnTransformer → LogisticRegression).
        feature_names: Ordered feature list fed to the pipeline.
        n_pos: Positive training examples.
        n_neg: Negative training examples.
        train_auc: ROC-AUC on training data (not held-out; diagnostic only).
    """

    pipeline: Pipeline
    feature_names: list[str]
    n_pos: int
    n_neg: int
    train_auc: float


_FITTED: AcceptanceModel | None = None


def _build_labeled_dataset(conn: Any) -> pd.DataFrame:
    """Join trade_rumors with transactions to assign weak accept/reject labels.

    Returns a DataFrame with columns:
      bref_code, war_buyer_bias, avg_age_received, deadline_pct, cluster_id,
      accepted (0 or 1).
    """
    rumors = conn.execute(
        """
        SELECT
            r.url,
            r.post_date,
            r.teams_mentioned,
            r.players_mentioned,
            r.slug
        FROM trade_rumors r
        WHERE r.is_trade_rumor = true
        """
    ).fetchdf()

    if rumors.empty:
        logger.warning("no trade_rumor rows in trade_rumors table — cannot fit")
        return pd.DataFrame()

    # Get all trade transactions for fast join
    txns = conn.execute(
        """
        SELECT DISTINCT
            t.date,
            t.to_team_name,
            t.player_name,
            t.player_id
        FROM transactions t
        WHERE t.type_code = 'TR'
          AND t.player_id IS NOT NULL
          AND t.to_team_name IS NOT NULL
        """
    ).fetchdf()

    # GM profiles keyed by bref_code
    profiles = conn.execute(
        """
        SELECT
            gp.bref_code,
            gp.war_buyer_bias,
            gp.avg_age_received,
            gp.deadline_pct,
            ga.cluster_id
        FROM gm_behavioral_profiles gp
        JOIN gm_archetypes ga USING (regime_id)
        """
    ).fetchdf()

    if profiles.empty:
        logger.warning("no GM profiles found — cannot fit")
        return pd.DataFrame()

    txn_dates = (
        pd.to_datetime(txns["date"]) if not txns.empty else pd.Series([], dtype="datetime64[ns]")
    )

    rows: list[dict[str, Any]] = []
    for _, rumor in rumors.iterrows():
        try:
            teams: list[str] = json.loads(rumor["teams_mentioned"] or "[]")
            players: list[str] = json.loads(rumor["players_mentioned"] or "[]")
        except (json.JSONDecodeError, TypeError):
            continue

        post_date = pd.to_datetime(rumor["post_date"])
        window_end = post_date + timedelta(days=_MATCH_WINDOW_DAYS)

        # Weak label: did any transaction in the window mention a player token from this rumor?
        accepted = 0
        if not txns.empty and players:
            in_window = (txn_dates >= post_date) & (txn_dates <= window_end)
            window_players = set(
                txns.loc[in_window, "player_name"].dropna().str.lower().str.replace(" ", "-")
            )
            if any(p in window_players for p in players):
                accepted = 1

        # Emit one row per mentioned team (the "receiving" GM context)
        for bref in teams:
            prof_rows = profiles[profiles["bref_code"] == bref]
            if prof_rows.empty:
                continue
            prof = prof_rows.iloc[-1]  # most recent regime
            rows.append(
                {
                    "bref_code": bref,
                    "war_buyer_bias": float(prof["war_buyer_bias"] or 0.0),
                    "avg_age_received": float(prof["avg_age_received"] or 29.0),
                    "deadline_pct": float(prof["deadline_pct"] or 0.0),
                    "cluster_id": str(int(prof["cluster_id"])),
                    "accepted": accepted,
                }
            )

    return pd.DataFrame(rows)


def fit() -> AcceptanceModel:
    """Train the acceptance model on labeled rumor data.

    Reads trade_rumors + transactions + gm_behavioral_profiles from the DB.
    Stores the fitted model in the module-level ``_FITTED`` slot.

    Returns:
        Fitted AcceptanceModel.

    Raises:
        RuntimeError: If insufficient training data (< 10 examples of each class).
    """
    global _FITTED

    with db.connect(read_only=True) as conn:
        df = _build_labeled_dataset(conn)

    if df.empty:
        raise RuntimeError("empty training dataset — run 'ste ingest mlbtr' first")

    n_pos = int((df["accepted"] == 1).sum())
    n_neg = int((df["accepted"] == 0).sum())
    logger.info("acceptance model: %d pos / %d neg examples", n_pos, n_neg)

    if n_pos < 10 or n_neg < 10:
        raise RuntimeError(
            f"insufficient training data: {n_pos} positives, {n_neg} negatives "
            f"(need ≥10 of each). Run 'ste ingest mlbtr' to populate trade_rumors."
        )

    x_train = df[_NUMERIC_FEATURES + _CATEGORICAL_FEATURES]
    y = df["accepted"].to_numpy()

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), _NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                _CATEGORICAL_FEATURES,
            ),
        ]
    )
    pipeline = Pipeline(
        steps=[
            ("pre", preprocessor),
            ("clf", LogisticRegression(C=1.0, max_iter=500, random_state=42)),
        ]
    )
    pipeline.fit(x_train, y)

    from sklearn.metrics import roc_auc_score  # lazy import — only needed here

    proba = pipeline.predict_proba(x_train)[:, 1]
    try:
        train_auc = float(roc_auc_score(y, proba))
    except ValueError:
        train_auc = float("nan")

    _FITTED = AcceptanceModel(
        pipeline=pipeline,
        feature_names=_NUMERIC_FEATURES + _CATEGORICAL_FEATURES,
        n_pos=n_pos,
        n_neg=n_neg,
        train_auc=train_auc,
    )
    logger.info("acceptance model fitted: train AUC=%.3f", train_auc)
    return _FITTED


def predict_proba(
    bref_code: str,
    war_buyer_bias: float,
    avg_age_received: float,
    deadline_pct: float,
    cluster_id: int,
) -> float:
    """Return P(accept) for a GM profile.

    Args:
        bref_code: Baseball Reference team code (unused in prediction; for logging).
        war_buyer_bias: GM's WAR-acquisition tendency.
        avg_age_received: GM's preferred player age at acquisition.
        deadline_pct: Fraction of trades at the deadline.
        cluster_id: GM archetype cluster (0-indexed integer).

    Returns:
        Probability in [0, 1].

    Raises:
        RuntimeError: If model not yet fitted.
    """
    if _FITTED is None:
        raise RuntimeError("call gm_acceptance.fit() before predict_proba()")

    row = pd.DataFrame(
        [
            {
                "war_buyer_bias": war_buyer_bias,
                "avg_age_received": avg_age_received,
                "deadline_pct": deadline_pct,
                "cluster_id": str(cluster_id),
            }
        ]
    )
    proba = _FITTED.pipeline.predict_proba(row)[0, 1]
    logger.debug("acceptance P(%s)=%.3f", bref_code, proba)
    return float(proba)


def predict_proba_from_profile(bref_code: str) -> float | None:
    """Look up a GM profile by team code and return P(accept).

    Returns None if the team has no profile or the model is not fitted.
    """
    if _FITTED is None:
        return None

    with db.connect(read_only=True) as conn:
        row = conn.execute(
            """
            SELECT
                gp.war_buyer_bias,
                gp.avg_age_received,
                gp.deadline_pct,
                ga.cluster_id
            FROM gm_behavioral_profiles gp
            JOIN gm_archetypes ga USING (regime_id)
            WHERE gp.bref_code = ?
            ORDER BY gp.regime_end DESC
            LIMIT 1
            """,
            [bref_code],
        ).fetchone()

    if row is None:
        return None

    return predict_proba(
        bref_code=bref_code,
        war_buyer_bias=float(row[0] or 0.0),
        avg_age_received=float(row[1] or 29.0),
        deadline_pct=float(row[2] or 0.0),
        cluster_id=int(row[3]),
    )
