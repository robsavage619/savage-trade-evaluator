"""Enrich current_players.json with calibrated Python valuations.

Reads the roster seed and, for every position player and pitcher, attaches the
canonical ``value_player`` outputs — regressed (role-calibrated shrinkage) and
leverage-adjusted projected WAR plus control-window surplus — so the frontend
reads these numbers instead of recomputing surplus from raw last-season WAR.
No network; reproducible from the local DuckDB.

Run:
    uv run python scripts/enrich_player_projection.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from savage_trade_evaluator.modeling.value_player import value_player
from savage_trade_evaluator.storage.db import connect

logger = logging.getLogger(__name__)

SEED_PATH = (
    Path(__file__).resolve().parent.parent
    / "frontend"
    / "src"
    / "data"
    / "seed"
    / "current_players.json"
)


def _debut_year(debut: str | None) -> int | None:
    if not debut or len(debut) < 4:
        return None
    try:
        return int(debut[:4])
    except ValueError:
        return None


def _load_contracts(conn, season: int) -> dict[int, tuple[str | None, int | None]]:
    """Map mlb_player_id -> (contract_status, cap_hit) from Spotrac for a season.

    The active-table row carries the real arb/veteran status and cap hit that the
    roster seed lacked (it predated the 30-team Spotrac ingest). Feeding these to
    ``value_player`` gives correct arb classes and surfaces guaranteed-contract
    liabilities instead of pricing every veteran as break-even.
    """
    rows = conn.execute(
        "SELECT mlb_player_id, status, cap_hit FROM spotrac_player_contracts "
        "WHERE season = ? AND table_type = 'active' AND mlb_player_id IS NOT NULL",
        [season],
    ).fetchall()
    return {int(pid): (status, cap) for pid, status, cap in rows}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seed = json.loads(SEED_PATH.read_text())
    season = int(seed.get("season_used_for_war") or 0) or 2026

    enriched = 0
    skipped_no_data = 0
    with connect(read_only=True) as conn:
        contracts = _load_contracts(conn, season)
        for team in seed["teams"]:
            for p in team["players"]:
                pid = p.get("mlb_player_id")
                age = p.get("age")
                if pid is None or age is None or not p.get("position_abbr"):
                    continue
                status, cap = contracts.get(int(pid), (None, None))
                contract_status = status or p.get("contract_status")
                cap_hit = cap if cap is not None else p.get("cap_hit")
                if contract_status is not None:
                    p["contract_status"] = contract_status
                if cap_hit is not None:
                    p["cap_hit"] = cap_hit
                v = value_player(
                    int(pid),
                    season,
                    contract_status,
                    p.get("position_abbr"),
                    float(age),
                    cap_hit=cap_hit,
                    debut_year=_debut_year(p.get("mlb_debut_date")),
                    conn=conn,
                )
                if v.seasons_used == 0:
                    skipped_no_data += 1
                    continue
                p["projected_war"] = round(v.projected_war, 2)
                p["valued_war"] = round(v.valued_war, 2)
                p["is_reliever"] = v.is_reliever
                p["years_controlled"] = v.years_controlled
                p["surplus_war"] = round(v.surplus_war, 2)
                p["surplus_dollars"] = round(v.surplus_dollars, 0)
                p["yr1_cost"] = round(v.control_salaries[0], 0) if v.control_salaries else 0
                enriched += 1

    seed["projection_enriched"] = True
    SEED_PATH.write_text(json.dumps(seed, indent=2, default=str))
    logger.info(
        "enriched %d players (%d skipped, no bWAR history) -> %s",
        enriched,
        skipped_no_data,
        SEED_PATH.name,
    )


if __name__ == "__main__":
    main()
