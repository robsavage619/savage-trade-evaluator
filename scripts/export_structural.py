"""Export the structural model to the frontend as data.

Writes, under ``frontend/src/data/model/``:

  structural_model.json   model parameters, per-player features, as-of date
  structural_golden.json  forecasts computed here from those exact numbers, which
                          ``frontend/scripts/check-structural.mjs`` reproduces in
                          TypeScript

Per-player features are priced as if each player were acquired today, or as of the
last bWAR data date when the latest season is partial (see ``hypothetical_legs``).

Run:
  uv run python scripts/export_structural.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np

from savage_trade_evaluator.modeling import structural

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "frontend/src/data/seed/current_players.json"
OUT = ROOT / "frontend/src/data/model"
PLAYER_FIELDS = ["held_ctrl_war", "held_post_war", "n_no_mlb", "rate"]
N_SIDE_CASES = 40
N_PAIR_CASES = 15


def side_features(players: dict[str, list[float]], ids: list[str]) -> dict[str, float]:
    """Summed structural features for a package, from the rounded exported numbers."""
    rows = np.array([players[i] for i in ids])
    return {
        "held_ctrl_war": float(rows[:, 0].sum()),
        "held_post_war": float(rows[:, 1].sum()),
        "n_legs": float(len(ids)),
        "n_no_mlb": float(rows[:, 2].sum()),
    }


def main() -> None:
    roster = json.loads(ROSTER.read_text())
    ids = sorted({int(p["mlb_player_id"]) for t in roster["teams"] for p in t["players"]})
    legs, note, as_of = structural.hypothetical_legs(ids, date.today())
    players = {
        str(int(r.mlb_player_id)): [
            round(float(r.held_ctrl_war), 4),
            round(float(r.held_post_war), 4),
            int(r.n_no_mlb),
            round(float(r.rate), 4),
        ]
        for r in legs.itertuples(index=False)
    }
    params = structural.export_params(structural.production_fit())
    model = {
        "as_of": as_of.isoformat(),
        "note": note,
        "train_end_season": structural.TRAIN_END_SEASON,
        "player_fields": PLAYER_FIELDS,
        "params": params,
        "players": players,
    }

    rng = np.random.default_rng(7)
    keys = sorted(players)

    def package(size: int) -> list[str]:
        return [str(k) for k in rng.choice(keys, size=size, replace=False)]

    def atoms(pkg: list[str]) -> tuple[np.ndarray, np.ndarray]:
        return structural.side_atoms(params, side_features(players, pkg))

    sides, pairs = [], []
    for i in range(N_SIDE_CASES):
        pkg = package(1 + i % 6)
        sides.append({"ids": pkg, "expected": structural.summarize_atoms(*atoms(pkg))})
    for i in range(N_PAIR_CASES):
        a, b = package(1 + i % 4), package(1 + (i + 2) % 5)
        diff = structural.difference_atoms(atoms(a), atoms(b))
        pairs.append({"a": a, "b": b, "expected": structural.summarize_atoms(*diff)})

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "structural_model.json").write_text(json.dumps(model, separators=(",", ":")))
    (OUT / "structural_golden.json").write_text(
        json.dumps({"sides": sides, "pairs": pairs}, separators=(",", ":"))
    )
    print(f"exported {len(players)} players, as of {as_of.isoformat()}")
    if note:
        print(note)


if __name__ == "__main__":
    main()
