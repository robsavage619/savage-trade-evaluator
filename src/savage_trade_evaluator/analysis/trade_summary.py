"""Trade-data summary statistics — answers Q-01/Q-02 empirically from V1 data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True, slots=True)
class TradeScopeCount:
    """How many trade-events meet a given filter, year by year."""

    label: str
    counts_by_season: dict[int, int]

    def total(self) -> int:
        """Sum of counts across all seasons in this filter."""
        return sum(self.counts_by_season.values())


def trades_per_season() -> TradeScopeCount:
    """Affiliated MLB trade events per season."""
    with db.connect(read_only=True) as conn:
        rows = conn.execute(
            "SELECT season, COUNT(*) FROM trade_events_affiliated "
            "GROUP BY season ORDER BY season"
        ).fetchall()
    return TradeScopeCount(
        label="affiliated trades",
        counts_by_season={int(s): int(n) for s, n in rows},
    )


def trades_with_war_player(min_war_t_minus_1: float = 2.0) -> TradeScopeCount:
    """Trade events involving at least one player above a prior-season WAR threshold."""
    with db.connect(read_only=True) as conn:
        rows = conn.execute(
            """
            SELECT trade_season, COUNT(DISTINCT trade_event_id)
            FROM trade_player_war_window
            WHERE war_t_minus_1 >= ?
              AND from_team_bref IS NOT NULL AND to_team_bref IS NOT NULL
            GROUP BY trade_season ORDER BY trade_season
            """,
            [min_war_t_minus_1],
        ).fetchall()
    return TradeScopeCount(
        label=f"trades with ≥{min_war_t_minus_1} WAR player",
        counts_by_season={int(s): int(n) for s, n in rows},
    )


def war_outcome_window_summary(window_years: int = 3) -> pd.DataFrame:
    """Return one row per trade-leg with the sum of WAR over the post-trade outcome window."""
    cols = ["war_t_with_receiver"] + [f"war_t_plus_{i}" for i in range(1, window_years + 1)]
    coalesce_sum = " + ".join(f"COALESCE({c}, 0)" for c in cols)
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            f"""
            SELECT trade_event_id, leg_index, date, trade_season,
                   player_name, from_team_bref, to_team_bref,
                   war_t_minus_1,
                   {coalesce_sum} AS war_outcome_sum
            FROM trade_player_war_window
            WHERE from_team_bref IS NOT NULL AND to_team_bref IS NOT NULL
              AND trade_season <= 2024 - ?
            """,
            [window_years],
        ).df()
    return df


def biggest_dev_fit_jumps(season: int, top_n: int = 10) -> pd.DataFrame:
    """Pitchers traded in `season` who saw the biggest K-percentile-rank jump after the trade."""
    with db.connect(read_only=True) as conn:
        df = conn.execute(
            """
            SELECT player_name,
                   from_team_bref AS from_team,
                   to_team_bref AS to_team,
                   k_percent_t_minus_1,
                   k_percent_t_plus_1,
                   k_percent_t_plus_1 - k_percent_t_minus_1 AS k_pct_jump,
                   whiff_percent_t_minus_1,
                   whiff_percent_t_plus_1,
                   fb_spin_t_minus_1, fb_spin_t_plus_1,
                   curve_spin_t_minus_1, curve_spin_t_plus_1
            FROM trade_player_arsenal_window
            WHERE trade_season = ?
              AND k_percent_t_minus_1 IS NOT NULL
              AND k_percent_t_plus_1 IS NOT NULL
            ORDER BY k_pct_jump DESC
            LIMIT ?
            """,
            [season, top_n],
        ).df()
    return df


def personnel_for_trade(trade_event_id: int) -> dict[str, pd.DataFrame]:
    """Return both-sides personnel snapshot for one trade event.

    Returns:
        Dict with two keys, each mapped to a DataFrame of (role, person):
        ``"from_side"`` and ``"to_side"``.
    """
    import pandas as pd

    with db.connect(read_only=True) as conn:
        event = conn.execute(
            """
            SELECT DISTINCT trade_event_id, date, trade_season,
                            from_team_id, from_team_bref,
                            to_team_id, to_team_bref
            FROM trade_player_unified
            WHERE trade_event_id = ?
            LIMIT 1
            """,
            [trade_event_id],
        ).fetchone()
        if event is None:
            return {}
        season = event[2]
        from_team_id, to_team_id = event[3], event[5]

        out: dict[str, pd.DataFrame] = {}
        for side, team_id in (("from_side", from_team_id), ("to_side", to_team_id)):
            fo = conn.execute(
                "SELECT 'FO' AS layer, role, person_name FROM front_office "
                "WHERE team_id = ? AND season = ?",
                [team_id, season],
            ).df()
            co = conn.execute(
                "SELECT 'CO' AS layer, job_title AS role, person_name FROM coaches "
                "WHERE team_id = ? AND season = ? AND job_code IN "
                "('MNGR','COAB','COAT','COAP','COAU','COAA','COA1','COA3')",
                [team_id, season],
            ).df()
            out[side] = pd.concat([fo, co], ignore_index=True)
    return out
