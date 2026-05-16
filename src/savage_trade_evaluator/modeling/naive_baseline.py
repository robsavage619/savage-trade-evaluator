"""Naïve baseline trade evaluator — pure WAR-based bilateral surplus.

This is **the model we explicitly want to beat.** Computes per-team surplus as
``WAR_received - WAR_given_up`` summed over a fixed outcome window, with no
context-aware terms (no contention adjustment, no dev-fit, no $/WAR conversion,
no playoff-revenue bump, no posterior — point estimate only).

The V2 context-aware multilevel model is built to close every gap this baseline
leaves open. The baseline's failure modes (cataloged after backtesting) become
V2's research agenda.

See ``docs/NAIVE_BASELINE.md`` for the design discussion. Notable simplifications
relative to BBtN Ch 5-2:

* **No dollar conversion.** We don't have Cot's contract data; can't compute
  implied WAR-at-price. Surplus is in raw WAR units.
* **No playoff-revenue bump** (BBtN Ch 5-2 two-tiered model). All wins are
  treated as equal.
* **No selection-on-gains adjustment.** Treats trades as randomly assigned —
  knowingly wrong (Mixtape Ch 4 ATT vs ATE) but documents the gap for V2.
* **Stays-with-team assumption for T+1+.** Uses season-total WAR for the
  outcome years; doesn't split if the player gets re-traded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb


@dataclass(frozen=True, slots=True)
class TeamLedger:
    """Per-team WAR ledger for one trade event."""

    team_bref: str
    war_received: float
    war_given_up: float
    players_received: tuple[str, ...] = field(default_factory=tuple)
    players_given_up: tuple[str, ...] = field(default_factory=tuple)

    @property
    def surplus(self) -> float:
        """Net WAR this team got from the trade over the outcome window."""
        return self.war_received - self.war_given_up


@dataclass(frozen=True, slots=True)
class TradeEvaluation:
    """Output of evaluating one trade event under the naïve baseline."""

    trade_event_id: int
    trade_season: int
    outcome_window_years: int
    team_ledgers: tuple[TeamLedger, ...]

    @property
    def winning_team(self) -> str | None:
        """The bref code of the team that gained the most WAR. ``None`` on tie/empty."""
        if not self.team_ledgers:
            return None
        best = max(self.team_ledgers, key=lambda t: t.surplus)
        return best.team_bref


def _player_outcome_war(
    conn: duckdb.DuckDBPyConnection,
    mlb_player_id: int,
    trade_season: int,
    outcome_window_years: int,
    *,
    receiver_bref: str | None = None,
) -> float:
    """Sum a player's WAR over the post-trade outcome window.

    Args:
        conn: Open read-only DuckDB connection.
        mlb_player_id: MLB Stats API player ID.
        trade_season: 4-digit year the trade occurred in.
        outcome_window_years: How many *full* post-trade seasons to include
            (T+1, T+2, ..., T+N). The trade year itself is included as the
            receiver's portion only (``war_t_with_receiver``) when
            ``receiver_bref`` is supplied.
        receiver_bref: If provided, include the trade-year split with this
            receiving team. Otherwise the trade-year contribution is 0.

    Returns:
        Sum of WAR over the configured window. NULL components treated as 0.
    """
    cols = [f"COALESCE(war_t_plus_{i}, 0)" for i in range(1, outcome_window_years + 1)]
    if receiver_bref is not None:
        cols.append("COALESCE(war_t_with_receiver, 0)")
    expr = " + ".join(cols)
    sql = f"""
        SELECT MAX({expr}) AS war_sum
        FROM trade_player_war_window
        WHERE mlb_player_id = ?
          AND trade_season = ?
          {"AND to_team_bref = ?" if receiver_bref is not None else ""}
    """
    params: list[object] = [mlb_player_id, trade_season]
    if receiver_bref is not None:
        params.append(receiver_bref)
    row = conn.execute(sql, params).fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def evaluate(
    trade_event_id: int,
    outcome_window_years: int = 3,
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> TradeEvaluation | None:
    """Run the naïve baseline on one trade event.

    Args:
        trade_event_id: The ``transaction_id`` shared across legs of one trade.
        outcome_window_years: Length of the post-trade WAR window (default 3
            per the Q-02 leaning in the decisions log).
        conn: Optional open connection. If omitted a read-only one is created
            and closed in this function.

    Returns:
        ``TradeEvaluation`` if the trade has at least one MLB-affiliated leg
        with team bref codes; ``None`` otherwise.
    """
    if conn is None:
        with db.connect(read_only=True) as opened:
            return evaluate(trade_event_id, outcome_window_years=outcome_window_years, conn=opened)

    legs = conn.execute(
        """
        SELECT mlb_player_id, player_name, from_team_bref, to_team_bref, trade_season
        FROM trade_player_unified
        WHERE trade_event_id = ?
          AND from_team_bref IS NOT NULL AND to_team_bref IS NOT NULL
        ORDER BY leg_index
        """,
        [trade_event_id],
    ).fetchall()
    if not legs:
        return None

    season = int(legs[0][4])
    teams_seen: set[str] = set()
    war_received: dict[str, float] = {}
    war_given_up: dict[str, float] = {}
    received_names: dict[str, list[str]] = {}
    given_names: dict[str, list[str]] = {}

    def touch(team: str) -> None:
        if team in teams_seen:
            return
        teams_seen.add(team)
        war_received[team] = 0.0
        war_given_up[team] = 0.0
        received_names[team] = []
        given_names[team] = []

    for player_id, player_name, from_bref, to_bref, _ in legs:
        if player_id is None:
            continue
        war_to = _player_outcome_war(
            conn,
            mlb_player_id=int(player_id),
            trade_season=season,
            outcome_window_years=outcome_window_years,
            receiver_bref=to_bref,
        )
        war_from = _player_outcome_war(
            conn,
            mlb_player_id=int(player_id),
            trade_season=season,
            outcome_window_years=outcome_window_years,
            receiver_bref=None,
        )
        touch(to_bref)
        touch(from_bref)
        war_received[to_bref] += war_to
        war_given_up[from_bref] += war_from
        received_names[to_bref].append(player_name or f"#{player_id}")
        given_names[from_bref].append(player_name or f"#{player_id}")

    ledgers = tuple(
        TeamLedger(
            team_bref=team,
            war_received=war_received[team],
            war_given_up=war_given_up[team],
            players_received=tuple(received_names[team]),
            players_given_up=tuple(given_names[team]),
        )
        for team in sorted(teams_seen)
    )
    return TradeEvaluation(
        trade_event_id=trade_event_id,
        trade_season=season,
        outcome_window_years=outcome_window_years,
        team_ledgers=ledgers,
    )
