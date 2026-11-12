"""R-66: does roster displacement add to the structural captured_war model?

Pre-registered before any spec was scored. The mechanism: a player is worth less
to a club that already has someone good at his position, because he plays less.

Incumbent strength, per acquired player: the mean WAR of the top-k players in his
position group on the receiving club in the season before his first season with
it, excluding him, with empty slots counted as zero. Groups and slots:

  C 1, 1B 1, 2B 1, 3B 1, SS 1, OF (LF, CF, RF) 3, SP 5, RP 6

Hitters are grouped by MLB primary position. Pitchers are SP if they started at
least half their games that season, else RP; an acquired pitcher takes his role
from his most recent pitching season. Designated hitters, unknown positions and
players with no MLB history have no incumbent and contribute nothing.

Side-level features (R is a player's 3-2-1 WAR rate, held is rate x seasons held):

  D1  held-WAR-weighted mean incumbent strength across the side's players
  D2  D1 (z-scored on the training fold) x the side's held WAR
  D3  displaced WAR = sum of held x min(incumbent / R, 1), for players with R > 0

Specs, each added to the structural model (S0):
  P1  S0 + D1
  P2  S0 + D2
  P3  S0 + D3

Decision rule: a spec earns a single look at the 2018-2021 holdout only if its
paired per-side CRPS gain over S0 on the pre-2018 folds has a 99% interval above
zero and it improves in at least 3 of the 4 folds. Otherwise displacement adds
nothing detectable and the holdout is not touched.

Run:
  uv run python scripts/r66_displacement.py
"""

# pyright: reportCallIssue=false, reportArgumentType=false, reportReturnType=false

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from savage_trade_evaluator.modeling import structural
from savage_trade_evaluator.modeling.metrics import crps_empirical
from savage_trade_evaluator.modeling.v3 import assemble_v3_combined
from savage_trade_evaluator.storage import db

TARGET = structural.TARGET
KEYS = structural.KEYS
BASE = list(structural.FEATURES)
HOLDOUT = (2018, 2021)
CV_TEST_SEASONS = (2014, 2015, 2016, 2017)
N_DRAWS = 400
Z_99 = 2.576

HITTER_GROUP = {
    "2": "C",
    "3": "1B",
    "4": "2B",
    "5": "3B",
    "6": "SS",
    "7": "OF",
    "8": "OF",
    "9": "OF",
    "O": "OF",
}
SLOTS = {"C": 1, "1B": 1, "2B": 1, "3B": 1, "SS": 1, "OF": 3, "SP": 5, "RP": 6}

_ROSTER_SQL = """
SELECT r.role, r.mlb_id, r.year_id, r.team_id, r.g, r.gs, COALESCE(r.war, 0) AS war,
       p.primary_position_code AS code
FROM (
    SELECT 'B' AS role, mlb_id, year_id, team_id, g, 0 AS gs, war FROM bwar_batting
    UNION ALL
    SELECT 'P', mlb_id, year_id, team_id, g, gs, war FROM bwar_pitching
) r
JOIN mlb_people p ON p.mlb_player_id = r.mlb_id
WHERE r.year_id BETWEEN 2007 AND 2021
"""


def roster_groups() -> tuple[dict, dict]:
    """Per (team, season, group) list of (WAR, player), and per-player role history.

    Returns:
        (roster, role) where ``roster[(team, year, group)]`` is a list of
        ``(war, mlb_id)`` and ``role[(mlb_id, year)]`` is the player's group that year.
    """
    with db.connect(read_only=True) as conn:
        rows = conn.execute(_ROSTER_SQL).df()
    roster: dict[tuple[str, int, str], list[tuple[float, int]]] = defaultdict(list)
    role: dict[tuple[int, int], str] = {}
    for r in rows.itertuples(index=False):
        if r.role == "B":
            group = HITTER_GROUP.get(str(r.code))
        elif str(r.code) == "1":
            group = "SP" if r.g and r.gs / r.g >= 0.5 else "RP"
        else:
            group = None
        if group is None:
            continue
        roster[(r.team_id, int(r.year_id), group)].append((float(r.war), int(r.mlb_id)))
        role[(int(r.mlb_id), int(r.year_id))] = group
    return roster, role


def incumbent_strength(roster: dict, team: str, season: int, group: str, exclude: int) -> float:
    """Mean WAR of the top-k players in ``group`` on ``team`` in ``season``, excluding one."""
    wars = sorted(
        (w for w, pid in roster.get((team, season, group), []) if pid != exclude), reverse=True
    )
    k = SLOTS[group]
    return float(sum(wars[:k]) / k)


def displacement_features() -> pd.DataFrame:
    """D1, D2 inputs and D3 per trade side, keyed on ``KEYS``."""
    roster, role = roster_groups()
    with db.connect(read_only=True) as conn:
        legs = conn.execute(
            """
            SELECT trade_event_id, leg_index, to_team_bref AS receiver_bref, trade_season,
                   mlb_player_id, date
            FROM trade_player_unified
            WHERE to_team_bref IS NOT NULL AND trade_season BETWEEN 2010 AND ?
            """,
            [HOLDOUT[1]],
        ).df()
        legs = structural.player_features(legs, conn)
    rate = ((3 * legs["w1"] + 2 * legs["w2"] + legs["w3"]) / 6.0).to_numpy()
    held = (legs["held_ctrl_war"] + legs["held_post_war"]).to_numpy()
    inc = np.full(len(legs), np.nan)
    for i, leg in enumerate(legs.itertuples(index=False)):
        pid, season = int(leg.mlb_player_id), int(leg.first_season) - 1
        group = next(
            (role[(pid, y)] for y in range(season, season - 6, -1) if (pid, y) in role), None
        )
        if group is not None:
            inc[i] = incumbent_strength(roster, leg.receiver_bref, season, group, pid)
    has = ~np.isnan(inc)
    legs["inc_x_held"] = np.where(has, inc * held, 0.0)
    legs["held_with_inc"] = np.where(has, held, 0.0)
    legs["displaced"] = np.where(
        has & (rate > 0), held * np.minimum(inc / np.where(rate > 0, rate, 1), 1.0), 0.0
    )
    side = legs.groupby(KEYS, as_index=False)[["inc_x_held", "held_with_inc", "displaced"]].sum()
    side["D1"] = np.where(
        side["held_with_inc"] > 0, side["inc_x_held"] / side["held_with_inc"], np.nan
    )
    side["D3"] = side["displaced"]
    return side[[*KEYS, "D1", "D3"]]


def design(train: pd.DataFrame, test: pd.DataFrame, spec: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Feature matrices for one spec; D1 is z-scored on ``train`` only."""
    out = []
    for frame in (train, test):
        x = frame[BASE].astype("float64").copy()
        d1 = ((frame["D1"] - train["D1"].mean()) / train["D1"].std()).fillna(0.0)
        if spec == "P1":
            x["D1"] = d1
        elif spec == "P2":
            x["D1_x_held"] = d1 * (frame["held_ctrl_war"] + frame["held_post_war"])
        elif spec == "P3":
            x["displaced_war"] = frame["D3"].fillna(0.0)
        out.append(x)
    return out[0], out[1]


def side_crps(y: np.ndarray, draws: np.ndarray) -> np.ndarray:
    """Per-side CRPS, so specs can be compared as paired differences."""
    return np.array([crps_empirical(y[i : i + 1], draws[i : i + 1]) for i in range(len(y))])


def run(train: pd.DataFrame, test: pd.DataFrame, spec: str) -> tuple[np.ndarray, np.ndarray]:
    """Fit one spec on ``train``; return per-side CRPS and 90% coverage flags on ``test``."""
    x_train, x_test = design(train, test, spec)
    model = structural.fit(x_train, train[TARGET].to_numpy(dtype="float64"))
    draws, _ = structural.predict(model, x_test, np.random.default_rng(137), N_DRAWS)
    y = test[TARGET].to_numpy(dtype="float64")
    lo, hi = np.percentile(draws, [5, 95], axis=1)
    return side_crps(y, draws), ((y >= lo) & (y <= hi)).astype(float)


def main() -> None:
    df = assemble_v3_combined().dropna(subset=[TARGET])
    df = df[df["trade_season"] <= HOLDOUT[1]]
    df = df.merge(
        structural.side_features(structural.TRAIN_START_SEASON, HOLDOUT[1]), on=KEYS, how="left"
    )
    df = df.merge(displacement_features(), on=KEYS, how="left")
    # DuckDB row order is not stable; the inner CV splits depend on it.
    df = df.sort_values(KEYS).reset_index(drop=True)
    print(f"sides with a displacement feature: {df['D1'].notna().mean():.0%}")
    dev = df[df["trade_season"] < HOLDOUT[0]]
    folds = [(dev[dev["trade_season"] < s], dev[dev["trade_season"] == s]) for s in CV_TEST_SEASONS]
    specs = ["S0", "P1", "P2", "P3"]

    results = {s: [run(a, b, s) for a, b in folds] for s in specs}
    base = [c for c, _ in results["S0"]]
    rows = []
    for spec in specs:
        crps = [c for c, _ in results[spec]]
        gain = np.concatenate(base) - np.concatenate(crps)
        half = Z_99 * gain.std(ddof=1) / np.sqrt(len(gain)) if spec != "S0" else 0.0
        fold_gain = [float((b - c).mean()) for b, c in zip(base, crps, strict=True)]
        better = sum(g > 0 for g in fold_gain)
        rows.append(
            {
                "spec": spec,
                "CRPS": np.concatenate(crps).mean(),
                "gain vs S0": gain.mean(),
                "99% half-width": half,
                "folds better": None if spec == "S0" else better,
                "Cov90": np.concatenate([v for _, v in results[spec]]).mean(),
                "earns holdout": bool(spec != "S0" and gain.mean() - half > 0 and better >= 3),
            }
        )
    table = pd.DataFrame(rows).set_index("spec")
    print(f"WALK-FORWARD, test seasons {CV_TEST_SEASONS}, n={sum(len(t) for _, t in folds)} sides")
    print(table.round(4).to_string())

    winners = [r["spec"] for r in rows if r["earns holdout"]]
    if not winners:
        print("\nNo spec earned a holdout look: displacement adds nothing detectable.")
        return
    best = max(winners, key=lambda s: table.loc[s, "gain vs S0"])
    holdout = df[df["trade_season"] >= HOLDOUT[0]]
    out = {s: run(dev, holdout, s) for s in ("S0", best)}
    print(f"\nHOLDOUT {HOLDOUT[0]}-{HOLDOUT[1]}, n={len(holdout)} sides, {best} chosen on folds")
    for s, (c, v) in out.items():
        print(f"  {s}  CRPS {c.mean():.4f}  Cov90 {v.mean():.3f}")
    gain = out["S0"][0] - out[best][0]
    print(
        f"  paired gain {gain.mean():+.4f}  95% half-width {1.96 * gain.std(ddof=1) / np.sqrt(len(gain)):.4f}"
    )


if __name__ == "__main__":
    main()
