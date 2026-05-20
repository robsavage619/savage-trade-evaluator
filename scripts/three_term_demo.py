"""Three-term trade value demo — Pressly trade (trade_event_id=371509).

Runs ``evaluate()`` for both legs of the 2018 Ryan Pressly trade
(HOU and MIN) and prints the three-term breakdown per leg.
"""

from __future__ import annotations

from savage_trade_evaluator.modeling.three_term_value import evaluate
from savage_trade_evaluator.storage import db


def main() -> None:
    """Evaluate both legs of the Pressly trade and print term breakdowns."""
    trade_event_id = 371509

    with db.connect(read_only=True) as conn:
        legs = conn.execute(
            """
            SELECT DISTINCT to_team_bref, from_team_bref
            FROM trade_player_unified
            WHERE trade_event_id = ?
              AND from_team_bref IS NOT NULL
              AND to_team_bref   IS NOT NULL
            """,
            [trade_event_id],
        ).fetchall()

    if not legs:
        print(f"No legs found for trade_event_id={trade_event_id}")
        return

    receiver_brefs: list[str] = sorted({row[0] for row in legs})

    print(f"=== Three-Term Trade Value: trade_event_id={trade_event_id} ===")
    print()

    for receiver_bref in receiver_brefs:
        result = evaluate(trade_event_id, receiver_bref)
        print(f"Receiving team: {receiver_bref}")
        print(
            f"  Term 1 — cost-controlled surplus : ${result.cost_controlled_surplus:>14,.0f}"
        )
        print(
            f"  Term 2 — post-FA surplus         : ${result.post_fa_surplus:>14,.0f}"
        )
        print(
            f"  Term 3 — Δ playoff-prob × revenue: ${result.playoff_revenue_delta:>14,.0f}"
        )
        print(f"  ─────────────────────────────────────────────────────")
        print(f"  Total                            : ${result.total:>14,.0f}")
        print(f"  Notes: {result.notes}")
        print()


if __name__ == "__main__":
    main()
