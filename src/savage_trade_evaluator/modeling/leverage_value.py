"""Leverage-aware reliever valuation.

Pitcher bWAR is context-neutral: it credits run prevention regardless of the
game state in which those runs were prevented. That systematically *undervalues*
high-leverage relievers — an elite closer throwing 65 innings almost entirely in
one-run games swings far more win probability than his RA9-based WAR reflects,
and the trade market prices that premium even though WAR does not.

This module applies the standard leverage-index correction used to convert a
reliever's context-neutral value into game-context wins:

    leverage_weight = (1 + gmLI) / 2

where ``gmLI`` is the batters-faced-weighted average leverage index of the
appearances (from ``retrosheet_game_appearances.avg_li``). A league-average
reliever sits near gmLI ≈ 1.35 → weight ≈ 1.18; an elite closer near gmLI ≈ 1.6
→ weight ≈ 1.30. Starters enter at leverage 1.0 by construction, so no
correction is applied to them (weight = 1.0).

This is distinct from :mod:`role_adjustment`, which partials *post-trade*
deployment leverage out of a realized outcome for attribution and is barred
from the predictor path as target leakage. Here we use a player's *pre-decision*
historical leverage as a valuation input, which is not leakage: it describes the
asset being valued, not its post-trade outcome.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# Batters-faced-weighted league-average game leverage by role (retrosheet 2024-25).
# Fallbacks when a player has no retrosheet leverage history.
LEAGUE_RELIEVER_GMLI: float = 1.35
LEAGUE_STARTER_GMLI: float = 0.75

# Bound the multiplier so a tiny-sample extreme leverage figure can't dominate.
_MIN_WEIGHT: float = 0.70
_MAX_WEIGHT: float = 1.70


def leverage_weight(gm_li: float, *, is_reliever: bool) -> float:
    """Win-context weight for a pitcher's WAR given game-entering leverage.

    Applies the ``(1 + gmLI) / 2`` leverage-index correction to relievers only;
    starters enter at leverage 1.0 by construction and are returned unweighted.

    Args:
        gm_li: Batters-faced-weighted average leverage index (gmLI).
        is_reliever: Whether the value being weighted is relief value.

    Returns:
        A multiplier in ``[_MIN_WEIGHT, _MAX_WEIGHT]`` for relievers, or exactly
        1.0 for starters.
    """
    if not is_reliever:
        return 1.0
    weight = (1.0 + gm_li) / 2.0
    return max(_MIN_WEIGHT, min(_MAX_WEIGHT, weight))


def leverage_adjusted_war(war: float, gm_li: float, *, is_reliever: bool) -> float:
    """Convert context-neutral WAR into leverage-aware win value.

    Args:
        war: Context-neutral WAR (RA9-based bWAR).
        gm_li: Batters-faced-weighted average leverage index (gmLI).
        is_reliever: Whether ``war`` is relief value.

    Returns:
        Leverage-adjusted WAR. Equal to ``war`` for starters.
    """
    return war * leverage_weight(gm_li, is_reliever=is_reliever)


def player_game_leverage(
    mlb_player_id: int,
    seasons: tuple[int, ...],
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> tuple[float | None, bool]:
    """Look up a pitcher's batters-faced-weighted gmLI over the given seasons.

    Bridges ``mlb_player_id`` to the Retrosheet id via ``chadwick_register`` and
    aggregates ``retrosheet_game_appearances`` leverage, weighting by batters
    faced. Role is decided by which of relief/starting saw more batters faced.

    Args:
        mlb_player_id: MLBAM player id.
        seasons: Seasons to pool (e.g. the two seasons before a decision).
        conn: Optional open read-only connection.

    Returns:
        Tuple of ``(gmLI, is_reliever)``. ``gmLI`` is ``None`` when the player
        has no Retrosheet leverage rows in the window (caller falls back to a
        league baseline).
    """
    if conn is None:
        with db.connect(read_only=True) as opened:
            return player_game_leverage(mlb_player_id, seasons, conn=opened)

    if not seasons:
        return None, False

    placeholders = ", ".join("?" for _ in seasons)
    row = conn.execute(
        f"""
        WITH retro AS (
            SELECT retro_id FROM chadwick_register WHERE mlb_player_id = ?
        )
        SELECT
            SUM(g.n_batters_faced * g.avg_li) / NULLIF(SUM(g.n_batters_faced), 0) AS gm_li,
            SUM(CASE WHEN g.is_reliever THEN g.n_batters_faced ELSE 0 END)         AS relief_bf,
            SUM(CASE WHEN g.is_reliever THEN 0 ELSE g.n_batters_faced END)         AS start_bf
        FROM retrosheet_game_appearances g
        JOIN retro r ON r.retro_id = g.pitcher_id
        WHERE g.season IN ({placeholders})
        """,
        [mlb_player_id, *seasons],
    ).fetchone()

    if row is None or row[0] is None:
        return None, False

    gm_li = float(row[0])
    relief_bf = int(row[1]) if row[1] is not None else 0
    start_bf = int(row[2]) if row[2] is not None else 0
    return gm_li, relief_bf >= start_bf
