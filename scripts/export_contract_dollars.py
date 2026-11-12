"""Export each player's next-season salary from the Baseball-Reference snapshot.

Writes ``frontend/src/data/model/contract_dollars.json``: for every player the
snapshot lists with a dollar figure for its first season, one ``[kind, amount]``
pair, where kind is

  g  guaranteed salary
  o  option value, an assumption that the option is exercised
  a  Baseball-Reference's arbitration estimate
  p  a pre-arbitration year (no figure printed; the card uses the league minimum)

Free-agent and missing cells carry no dollar and are left out, so the card falls
back to its own projection for them. Keyed by MLBAM id and by everyone on the
pages, not by the roster seed, so it does not depend on a roster refresh.

Some Baseball-Reference ids, mostly recent call-ups, are missing from the id
bridge. Those rows are matched to ``mlb_people`` by exact normalized name, and only
against recently active people, so an old namesake cannot be picked up; a name
with no match or several matches stays unmatched and the card projects it.

Run:
  uv run python scripts/export_contract_dollars.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from savage_trade_evaluator.storage import db

OUT = Path(__file__).resolve().parents[1] / "frontend/src/data/model/contract_dollars.json"
RECENT = "2024-01-01"


def pick_dollar(kind: str, amount: int | None, option_value: int | None) -> tuple[str, int] | None:
    """The dollar figure a season cell offers, or None when it states none.

    Args:
        kind: Cell kind from the contracts parser.
        amount: Guaranteed dollars, buyout or arbitration estimate.
        option_value: Salary if an option is exercised.

    Returns:
        ``(code, dollars)`` with code ``g``, ``o``, ``a`` or ``p``.
    """
    if kind == "guaranteed" and amount is not None:
        return "g", int(amount)
    if kind == "option" and option_value is not None:
        return "o", int(option_value)
    if kind == "arb" and amount is not None:
        return "a", int(amount)
    if kind == "pre_arb":
        # No figure is printed, but the source states the year is pre-arbitration,
        # so the card prices it at the league minimum instead of a projected
        # arbitration salary.
        return "p", 0
    return None


def normalize(name: str) -> str:
    """Lowercase ASCII letters and spaces only, so accents and punctuation match."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", ascii_name.lower()).strip()


def main() -> None:
    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(as_of) FROM bref_contract_players").fetchone()
        if latest is None or latest[0] is None:
            raise SystemExit("no Baseball-Reference contract snapshot has been ingested")
        as_of = latest[0]
        first = conn.execute(
            "SELECT MIN(season) FROM bref_contract_years WHERE as_of = ?", [as_of]
        ).fetchone()
        if first is None or first[0] is None:
            raise SystemExit(f"snapshot {as_of} has no season cells")
        season = first[0]
        rows = conn.execute(
            "SELECT p.mlb_player_id, p.player_name, y.kind, y.amount, y.option_value "
            "FROM bref_contract_players p JOIN bref_contract_years y "
            "USING (team_bref, as_of, bref_id) WHERE p.as_of = ? AND y.season = ?",
            [as_of, season],
        ).fetchall()
        people = conn.execute(
            "SELECT mlb_player_id, full_name FROM mlb_people WHERE active "
            "OR last_played_date >= ? OR mlb_debut_date >= ?",
            [RECENT, RECENT],
        ).fetchall()

    by_name: dict[str, list[int]] = {}
    for pid, full_name in people:
        by_name.setdefault(normalize(full_name), []).append(int(pid))

    players: dict[str, list] = {}
    bridged = unmatched = 0
    for pid, name, kind, amount, option_value in rows:
        if pid is None:
            matches = by_name.get(normalize(name), [])
            if len(matches) != 1:
                unmatched += 1
                continue
            pid = matches[0]
            bridged += 1
        picked = pick_dollar(kind, amount, option_value)
        if picked is not None:
            players[str(int(pid))] = list(picked)

    OUT.write_text(
        json.dumps(
            {"as_of": str(as_of), "season": season, "players": players}, separators=(",", ":")
        )
    )
    counts = {c: sum(v[0] == c for v in players.values()) for c in "goap"}
    print(
        f"{season} dollars for {len(players)} players {counts}; "
        f"{bridged} rows matched by name, {unmatched} unmatched"
    )


if __name__ == "__main__":
    main()
