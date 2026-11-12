"""Export per-player contract and availability flags for the War Room.

Writes ``frontend/src/data/model/contract_flags.json``. Sources:

  * Baseball-Reference contract snapshot (``bref_contract_*``): the last guaranteed
    season, and the first option with its type, value and fallback.
  * ``spotrac_conflicts``: players Spotrac shows with a multi-year deal but that
    Baseball-Reference lists with no club, or with an option inside Spotrac's window.
  * The roster seed: injured-list status and the last season with MLB WAR.

These are facts the structural forecast cannot see. Only players with at least one
flag are written.

Run:
  uv run python scripts/export_contract_flags.py
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from savage_trade_evaluator.ingest.bref_contracts import (
    ContractYear,
    guaranteed_through,
    spotrac_conflicts,
)
from savage_trade_evaluator.storage import db

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "frontend/src/data/seed/current_players.json"
OUT = ROOT / "frontend/src/data/model/contract_flags.json"
IL_CODES = {"D7", "D10", "D15", "D60"}


def _norm(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", ascii_name.lower()).strip()


def main() -> None:
    roster = json.loads(ROSTER.read_text())
    seed_season = roster.get("season_used_for_war")
    players = {int(p["mlb_player_id"]): p for t in roster["teams"] for p in t["players"]}

    with db.connect(read_only=True) as conn:
        as_of = conn.execute("SELECT MAX(as_of) FROM bref_contract_players").fetchone()[0]
        rows = conn.execute(
            "SELECT p.mlb_player_id, p.player_name, p.service_time, y.season, y.kind, "
            "y.option_type, y.option_value, y.status_if_declined "
            "FROM bref_contract_players p JOIN bref_contract_years y "
            "USING (team_bref, as_of, bref_id) WHERE p.as_of = ? ORDER BY p.bref_id, y.season",
            [as_of],
        ).fetchall()
        conflicts = spotrac_conflicts(conn, as_of)

    # Group Baseball-Reference cells by player, by MLBAM id and by normalized name
    # (a few Baseball-Reference ids are missing from the id bridge).
    by_id: dict[int, list[tuple]] = {}
    by_name: dict[str, list[tuple]] = {}
    for r in rows:
        if r[0] is not None:
            by_id.setdefault(int(r[0]), []).append(r)
        else:
            by_name.setdefault(_norm(r[1]), []).append(r)

    issue = {int(r.mlb_player_id): r.issue for r in conflicts.itertuples(index=False)}
    out: dict[str, dict] = {}
    for pid, p in players.items():
        cells = by_id.get(pid) or by_name.get(_norm(p["name"]), [])
        years = [
            ContractYear(
                int(c[3]), c[4], option_type=c[5], option_value=c[6], status_if_declined=c[7]
            )
            for c in cells
        ]
        flag: dict[str, object] = {}
        through = guaranteed_through(years)
        if through is not None:
            flag["g"] = through
        options = [y for y in years if y.kind == "option"]
        if options:
            first = min(options, key=lambda y: y.season)
            flag["o"] = {
                "s": first.season,
                "t": first.option_type,
                "v": first.option_value,
                "f": first.status_if_declined,
            }
        if issue.get(pid) in {"absent_from_bref", "option_inside_window"}:
            flag["c"] = issue[pid]
        if p.get("status_code") in IL_CODES:
            flag["il"] = p["status_code"]
        last_year = p.get("last_year")
        if (
            isinstance(last_year, int)
            and isinstance(seed_season, int)
            and last_year <= seed_season - 2
        ):
            flag["ly"] = last_year
        if flag:
            out[str(pid)] = flag

    OUT.write_text(
        json.dumps(
            {
                "contracts_as_of": str(as_of),
                "roster_as_of": roster.get("refreshed_at"),
                "players": out,
            },
            separators=(",", ":"),
        )
    )
    kinds = {k: sum(k in f for f in out.values()) for k in ("g", "o", "c", "il", "ly")}
    print(f"flags for {len(out)} of {len(players)} rostered players: {kinds}")
    for name in ("Michael King", "Joe Musgrove", "Juan Soto"):
        pid = next((i for i, p in players.items() if p["name"] == name), None)
        print(f"  {name}: {out.get(str(pid))}")


if __name__ == "__main__":
    main()
