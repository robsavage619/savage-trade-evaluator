"""(Team, regime) cluster mapping for the V2 multilevel model.

Per D-28 the V2 architecture clusters on (team, regime) where regime is the
GM tenure. ``team_regime_assignments`` view provides ``regime_id`` per
(bref_code, season) for 1990+ trades (after the 2026-05-17 BR backfill).

Pre-1990 trades fall back to a "team_only" regime_id so the multilevel
partial pooling still works. This is per the D-28 implication note:
> Pre-2010 trades fall back to team-only clustering.

This module just exposes the lookup as a clean function. The actual
clustering happens in ``multilevel.py``.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false

from __future__ import annotations

import pandas as pd

from savage_trade_evaluator.storage import db

PRE_REGIME_PLACEHOLDER = "_team_only"


def load_regime_lookup() -> pd.DataFrame:
    """Return a DataFrame keyed on (bref_code, season) with regime_id."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT bref_code, season, regime_id, decision_maker
            FROM team_regime_assignments
            """
        ).df()
    return df


def attach_regime_id(trades_df: pd.DataFrame) -> pd.DataFrame:
    """Add ``regime_id`` column to a frame keyed on (receiver_bref, trade_season).

    Falls back to ``{bref_code}{PRE_REGIME_PLACEHOLDER}`` for seasons where
    no front_office record exists (pre-1990 historically; some teams missing
    a season here and there).
    """
    lookup = load_regime_lookup()
    merged = trades_df.merge(
        lookup,
        left_on=["receiver_bref", "trade_season"],
        right_on=["bref_code", "season"],
        how="left",
    )
    # Fallback: team-only regime when no front_office record exists.
    fallback = merged["receiver_bref"].astype(str) + PRE_REGIME_PLACEHOLDER
    merged["regime_id"] = merged["regime_id"].fillna(fallback)
    return merged.drop(columns=["bref_code", "season"], errors="ignore")
