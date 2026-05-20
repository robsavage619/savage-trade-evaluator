"""Three-term trade value formula (D-09 refinement).

Three valuations per player at any decision point:
  1. Cost-controlled surplus: WAR delivered × $/WAR − actual salary (pre-arb/arb underpay)
  2. Post-FA surplus: projected WAR × market $/WAR − projected FA salary (stub: requires FA projection model)
  3. Δ playoff-prob × revenue: playoff probability delta × marginal playoff revenue (stub: requires playoff model)

Term 1 is live. Terms 2 and 3 are stubs returning 0.0 pending the FA projection
and playoff-revenue models planned for Phase 3.

See ``docs/NAIVE_BASELINE.md`` for $/WAR calibration anchors (~$8M/WAR in 2024 dollars).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb


@dataclass(frozen=True, slots=True)
class ThreeTermValue:
    """Three-term trade value for one receiving team's leg of a trade.

    Attributes:
        trade_event_id: The transaction_id shared across legs of one trade.
        receiver_bref: Baseball Reference team code for the receiving team.
        cost_controlled_surplus: Term 1 — WAR surplus during cost-control years
            in dollars (realized WAR × $/WAR − actual salary paid).
        post_fa_surplus: Term 2 — projected surplus post-FA in dollars.
            Stub: 0.0 until the FA projection model exists.
        playoff_revenue_delta: Term 3 — Δ playoff-probability × marginal playoff
            revenue in dollars. Stub: 0.0 until the playoff model exists.
        total: Sum of all three terms.
        notes: Human-readable explanation of any stubbed or missing terms.
    """

    trade_event_id: int
    receiver_bref: str
    cost_controlled_surplus: float
    post_fa_surplus: float
    playoff_revenue_delta: float
    total: float
    notes: str


def compute_cost_controlled_surplus(
    trade_event_id: int,
    receiver_bref: str,
    outcome_window_years: int = 3,
    dollars_per_war: float = 8_000_000.0,
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> tuple[float, str]:
    """Compute term 1: realized WAR × $/WAR − actual salary during cost-control period.

    Queries ``trade_player_war_window`` for realized WAR and joins to
    ``bwar_batting`` / ``bwar_pitching`` for salary data. If salary is missing
    or null for any player-season, that player's salary contribution is treated
    as 0 and noted.

    Args:
        trade_event_id: The transaction_id shared across legs of one trade.
        receiver_bref: Baseball Reference team code for the receiving team.
        outcome_window_years: Number of post-trade seasons to sum (T+1 … T+N).
        dollars_per_war: Dollar value per WAR (default 8M = ~2024 FA market).
        conn: Optional open DuckDB connection. If omitted, a read-only one is
            opened and closed within this call.

    Returns:
        Tuple of (surplus_dollars, notes_string). Notes is empty string if
        everything resolved cleanly.
    """
    if conn is None:
        with db.connect(read_only=True) as opened:
            return compute_cost_controlled_surplus(
                trade_event_id,
                receiver_bref,
                outcome_window_years=outcome_window_years,
                dollars_per_war=dollars_per_war,
                conn=opened,
            )

    # Build the WAR sum expression over T+1 … T+N (plus trade-year split)
    war_cols = [f"COALESCE(w.war_t_plus_{i}, 0)" for i in range(1, outcome_window_years + 1)]
    war_cols.append("COALESCE(w.war_t_with_receiver, 0)")
    war_expr = " + ".join(war_cols)

    # Pull realized WAR per player received by this team, with salary from bwar.
    # trade_player_war_window already carries to_team_bref; join bwar on mlb_id.
    # Sum salary over [trade_season, trade_season + outcome_window_years].
    rows = conn.execute(
        f"""
        WITH received AS (
            SELECT
                w.mlb_player_id,
                w.trade_season,
                ({war_expr}) AS realized_war
            FROM trade_player_war_window w
            WHERE w.trade_event_id = ?
              AND w.to_team_bref   = ?
        ),
        salary_combined AS (
            SELECT mlb_id, year_id AS season, salary
            FROM bwar_batting
            WHERE salary IS NOT NULL
            UNION ALL
            SELECT mlb_id, year_id AS season, salary
            FROM bwar_pitching
            WHERE salary IS NOT NULL
        ),
        player_salary AS (
            SELECT
                r.mlb_player_id,
                r.realized_war,
                AVG(s.salary) FILTER (
                    WHERE s.season BETWEEN r.trade_season
                                      AND r.trade_season + ?
                ) AS avg_salary
            FROM received r
            LEFT JOIN salary_combined s ON s.mlb_id = r.mlb_player_id
            GROUP BY r.mlb_player_id, r.realized_war
        )
        SELECT
            SUM(realized_war)                                AS total_war,
            SUM(COALESCE(avg_salary, 0))                     AS total_salary,
            COUNT(*) FILTER (WHERE avg_salary IS NULL)       AS missing_salary_count,
            COUNT(*)                                          AS player_count
        FROM player_salary
        """,
        [trade_event_id, receiver_bref, outcome_window_years],
    ).fetchone()

    if rows is None or rows[0] is None:
        return 0.0, f"no players found for trade_event_id={trade_event_id}, receiver={receiver_bref}"

    total_war: float = float(rows[0]) if rows[0] is not None else 0.0
    total_salary: float = float(rows[1]) if rows[1] is not None else 0.0
    missing_count: int = int(rows[2]) if rows[2] is not None else 0
    player_count: int = int(rows[3]) if rows[3] is not None else 0

    surplus = total_war * dollars_per_war - total_salary

    notes_parts: list[str] = []
    if missing_count > 0:
        notes_parts.append(
            f"salary missing for {missing_count}/{player_count} player(s) — treated as $0"
        )

    return surplus, "; ".join(notes_parts)


def evaluate(
    trade_event_id: int,
    receiver_bref: str,
    outcome_window_years: int = 3,
    dollars_per_war: float = 8_000_000.0,
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> ThreeTermValue:
    """Compute all three terms for one receiving-team leg of a trade.

    Term 1 (cost-controlled surplus) is computed from live data.
    Terms 2 and 3 are stubs returning 0.0 pending downstream models.

    Args:
        trade_event_id: The transaction_id shared across legs of one trade.
        receiver_bref: Baseball Reference team code for the receiving team.
        outcome_window_years: Number of post-trade seasons to sum (T+1 … T+N).
        dollars_per_war: Dollar value per WAR (default 8M = ~2024 FA market).
        conn: Optional open DuckDB connection. If omitted, a read-only one is
            opened and closed within this call.

    Returns:
        ``ThreeTermValue`` with term 1 live and terms 2/3 stubbed at 0.0.
    """
    if conn is None:
        with db.connect(read_only=True) as opened:
            return evaluate(
                trade_event_id,
                receiver_bref,
                outcome_window_years=outcome_window_years,
                dollars_per_war=dollars_per_war,
                conn=opened,
            )

    surplus_1, notes_1 = compute_cost_controlled_surplus(
        trade_event_id,
        receiver_bref,
        outcome_window_years=outcome_window_years,
        dollars_per_war=dollars_per_war,
        conn=conn,
    )

    stub_notes: list[str] = [
        "term2 (post-FA surplus) stubbed at 0.0 — requires FA projection model (Phase 3)",
        "term3 (playoff revenue delta) stubbed at 0.0 — requires playoff model (Phase 3)",
    ]
    if notes_1:
        stub_notes.insert(0, f"term1: {notes_1}")

    return ThreeTermValue(
        trade_event_id=trade_event_id,
        receiver_bref=receiver_bref,
        cost_controlled_surplus=surplus_1,
        post_fa_surplus=0.0,
        playoff_revenue_delta=0.0,
        total=surplus_1,
        notes="; ".join(stub_notes),
    )
