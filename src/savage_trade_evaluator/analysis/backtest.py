"""Backtest harness — runs a model over historical trades, persists results, surfaces residuals.

The naïve baseline is the inaugural model; V2 plugs in here identically.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from savage_trade_evaluator.modeling import naive_baseline
from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)


def run_naive_baseline(
    start_season: int = 2010,
    end_season: int = 2024,
    outcome_window_years: int = 3,
) -> int:
    """Evaluate every MLB-affiliated trade event in range and persist to DuckDB.

    Args:
        start_season: First trade season to evaluate (inclusive).
        end_season: Last trade season (inclusive). Trades whose outcome window
            extends beyond 2024 are still evaluated; trailing T+i years just
            return zeros for not-yet-existent seasons.
        outcome_window_years: How many T+i years to sum (default 3 per Q-02
            leaning).

    Returns:
        Number of (trade_event, team) rows written.
    """
    with db.connect(read_only=True) as conn:
        ids = conn.execute(
            """
            SELECT DISTINCT trade_event_id
            FROM trade_events_affiliated
            WHERE season BETWEEN ? AND ?
            ORDER BY trade_event_id
            """,
            [start_season, end_season],
        ).fetchall()

    logger.info("evaluating %d trade events with naive baseline", len(ids))

    rows: list[dict[str, object]] = []
    with db.connect(read_only=True) as conn:
        for (event_id,) in ids:
            result = naive_baseline.evaluate(
                int(event_id), outcome_window_years=outcome_window_years, conn=conn
            )
            if result is None:
                continue
            for ledger in result.team_ledgers:
                rows.append(
                    {
                        "trade_event_id": result.trade_event_id,
                        "trade_season": result.trade_season,
                        "outcome_window_years": result.outcome_window_years,
                        "team_bref": ledger.team_bref,
                        "war_received": round(ledger.war_received, 3),
                        "war_given_up": round(ledger.war_given_up, 3),
                        "surplus": round(ledger.surplus, 3),
                        "players_received": ", ".join(ledger.players_received),
                        "players_given_up": ", ".join(ledger.players_given_up),
                    }
                )

    import pandas as pd  # local

    df = pd.DataFrame(rows)
    with db.connect() as conn:
        schemas.initialize(conn)
        conn.execute(
            "DELETE FROM naive_baseline_results WHERE outcome_window_years = ?",
            [outcome_window_years],
        )
        conn.register("_staging_nbr", df)
        try:
            conn.execute(
                "INSERT INTO naive_baseline_results "
                "(trade_event_id, trade_season, outcome_window_years, team_bref, "
                "war_received, war_given_up, surplus, players_received, players_given_up) "
                "SELECT trade_event_id, trade_season, outcome_window_years, team_bref, "
                "war_received, war_given_up, surplus, players_received, players_given_up "
                "FROM _staging_nbr"
            )
        finally:
            conn.unregister("_staging_nbr")
    logger.info("wrote %d naive baseline rows", len(rows))
    return len(rows)


def top_surpluses(season: int | None = None, top_n: int = 15) -> pd.DataFrame:
    """Largest WAR-surplus rows from the most recent backtest run.

    Args:
        season: Optional season filter.
        top_n: Row cap.
    """
    where = "WHERE trade_season = ?" if season is not None else ""
    params: list[object] = [season] if season is not None else []
    params.append(top_n)
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT trade_event_id, trade_season, team_bref,
                   war_received, war_given_up, surplus,
                   players_received, players_given_up
            FROM naive_baseline_results
            {where}
            ORDER BY surplus DESC
            LIMIT ?
            """,
            params,
        ).df()
    return df


def bottom_surpluses(season: int | None = None, top_n: int = 15) -> pd.DataFrame:
    """Biggest WAR-deficit rows (the trades that look worst by naïve baseline)."""
    where = "WHERE trade_season = ?" if season is not None else ""
    params: list[object] = [season] if season is not None else []
    params.append(top_n)
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT trade_event_id, trade_season, team_bref,
                   war_received, war_given_up, surplus,
                   players_received, players_given_up
            FROM naive_baseline_results
            {where}
            ORDER BY surplus ASC
            LIMIT ?
            """,
            params,
        ).df()
    return df


def surplus_distribution() -> pd.DataFrame:
    """Per-season summary of naïve-baseline surpluses."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT trade_season,
                   COUNT(*) AS n_team_outcomes,
                   ROUND(AVG(surplus), 3) AS mean_surplus,
                   ROUND(median(surplus), 3) AS median_surplus,
                   ROUND(MIN(surplus), 3) AS worst,
                   ROUND(MAX(surplus), 3) AS best
            FROM naive_baseline_results
            GROUP BY trade_season
            ORDER BY trade_season
            """,
        ).df()
    return df
