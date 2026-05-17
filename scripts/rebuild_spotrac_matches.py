"""Rebuild Spotrac mlb_player_id matches using the upgraded normalizer.

Runs the two-pass match (exact + normalized) against existing
``spotrac_player_contracts`` rows and updates ``mlb_player_id`` in place.
No re-scrape — operates on already-stored raw rows. Reports before/after
match rate.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from savage_trade_evaluator.ingest.spotrac import _normalize_name
from savage_trade_evaluator.storage import db


def main() -> None:
    """Re-match all Spotrac contract rows to mlb_player_id."""
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM spotrac_player_contracts").fetchone()[0]
        before = conn.execute(
            "SELECT COUNT(*) FROM spotrac_player_contracts WHERE mlb_player_id IS NOT NULL"
        ).fetchone()[0]
        print(f"before: {before}/{total} = {100 * before / total:.2f}%")

        # Build the normalized index of mlb_people (only keys with a unique pid).
        people = conn.execute("SELECT mlb_player_id, full_name FROM mlb_people").fetchall()
        norm_index: dict[str, set[int]] = {}
        for pid, full_name in people:
            if full_name is None:
                continue
            key = _normalize_name(full_name)
            norm_index.setdefault(key, set()).add(pid)
        unique_index = {k: next(iter(v)) for k, v in norm_index.items() if len(v) == 1}

        # Pull every currently-unmatched distinct Spotrac player name.
        unmatched = conn.execute(
            "SELECT DISTINCT player_name FROM spotrac_player_contracts "
            "WHERE mlb_player_id IS NULL"
        ).fetchall()
        updates: list[tuple[int, str]] = []
        for (name,) in unmatched:
            pid = unique_index.get(_normalize_name(name))
            if pid is not None:
                updates.append((pid, name))

        print(f"resolving {len(updates)}/{len(unmatched)} previously-unmatched names")

        # Apply.
        for pid, name in updates:
            conn.execute(
                "UPDATE spotrac_player_contracts SET mlb_player_id = ? "
                "WHERE player_name = ? AND mlb_player_id IS NULL",
                (pid, name),
            )

        after = conn.execute(
            "SELECT COUNT(*) FROM spotrac_player_contracts WHERE mlb_player_id IS NOT NULL"
        ).fetchone()[0]
        print(f"after:  {after}/{total} = {100 * after / total:.2f}%")
        print(f"delta:  +{after - before} rows ({100 * (after - before) / total:.2f}pp)")


if __name__ == "__main__":
    main()
