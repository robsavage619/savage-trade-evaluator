"""Export the War Room data contract from DuckDB to JSON for the frontend.

Reads the trade-evaluator DuckDB (read-only) and writes per-club + league-index
JSON snapshots that the frontend imports directly (no live server). Signals are
transparent, vault-grounded heuristics computed for the current season, with
small-sample 2026 stats shrunk toward the 2025 full season (D-12 partial
pooling, McElreath ch12-13).

The ``scenarios`` slot is populated with Phase 2 model posteriors when
``--with-scenarios`` is passed. The first run trains and caches production fits
(slow: ~5 min). Subsequent runs load from cache (fast).

Run:
    uv run python scripts/export_warroom.py                  # fast, no scenarios
    uv run python scripts/export_warroom.py --with-scenarios  # includes posteriors
    uv run python scripts/export_warroom.py --warm-cache      # pre-train without exporting
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from savage_trade_evaluator.analysis import decline_drift
from savage_trade_evaluator.analysis import dev_system as dev_system_mod
from savage_trade_evaluator.modeling import gm_acceptance
from savage_trade_evaluator.modeling.scenario_engine import score_historical_scenarios
from savage_trade_evaluator.storage.db import connect

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SEASON = 2026
PRIOR_SEASON = 2025
OUT_DIR = Path(__file__).resolve().parent.parent / "frontend" / "src" / "data" / "warroom"

# --- Documented heuristic assumptions (tunable; replaced by Phase 2 model) ---

# 2026 Competitive Balance Tax base threshold (CBA 2022-2026). Static assumption
# pending an ingested source; payroll_context.luxury_tax_threshold is null for 2026.
CBT_THRESHOLD_2026 = 244_000_000

# Full-season WAR a contending roster should expect from each position slot.
# Tunable baseline; the Phase 2 model replaces this with a contextual posterior.
REPLACEMENT_BASELINE: dict[str, float] = {
    "C": 2.0,
    "1B": 2.0,
    "2B": 2.0,
    "3B": 2.5,
    "SS": 2.5,
    "LF": 2.0,
    "CF": 2.5,
    "RF": 2.0,
    "DH": 1.5,
    "SP": 12.0,  # rotation aggregate (~5 starters)
    "RP": 4.0,  # bullpen aggregate
}

# Static division map (stable reference data; standings table carries no division).
_DIVISION_TEAMS: dict[str, list[str]] = {
    "AL East": ["NYY", "BOS", "TBR", "TOR", "BAL"],
    "AL Central": ["CLE", "MIN", "DET", "KCR", "CHW"],
    "AL West": ["HOU", "SEA", "TEX", "LAA", "OAK"],
    "NL East": ["ATL", "NYM", "PHI", "MIA", "WSN"],
    "NL Central": ["MIL", "CHC", "STL", "CIN", "PIT"],
    "NL West": ["LAD", "SDP", "ARI", "SFG", "COL"],
}
DIVISIONS: dict[str, str] = {code: div for div, codes in _DIVISION_TEAMS.items() for code in codes}

# mlb_people.primary_position_code -> batting position bucket. Pitcher ("1") is
# handled separately via WAR-component attribution; two-way ("Y") bats as DH.
POSITION_MAP: dict[str, str] = {
    "2": "C",
    "3": "1B",
    "4": "2B",
    "5": "3B",
    "6": "SS",
    "7": "LF",
    "8": "CF",
    "9": "RF",
    "10": "DH",
    "O": "CF",  # generic outfield
    "Y": "DH",  # two-way player bats as DH
}

# MiLB position string -> bucket (farm proxy). "P"/"X" handled separately/skipped.
MILB_POSITION_MAP: dict[str, str] = {
    "C": "C",
    "1B": "1B",
    "2B": "2B",
    "3B": "3B",
    "SS": "SS",
    "LF": "LF",
    "CF": "CF",
    "RF": "RF",
    "DH": "DH",
}

# Farm proxy (upper-minors performance, labeled heuristic; not modeled WAR).
FARM_LEVEL_WEIGHT: dict[int, float] = {11: 1.0, 12: 0.55}  # AAA, AA proximity
FARM_HIT_K = 9.0  # OPS-over-level-mean -> WAR-equiv scale
FARM_CAP_PER = 1.2  # max WAR-equiv credited to a single prospect
FARM_POS_CAP = 2.5  # max total farm WAR-equiv credited to one position
FARM_MIN_PA = 100
FARM_MIN_IP = 20.0

AFFIL_CACHE = (
    Path(__file__).resolve().parent.parent / "data" / "duckdb" / f"affiliations_{SEASON}.json"
)

# Vault citations attached to each signal (kept in sync with ~/Vault/savage_vault/wiki).
CITES = {
    "window": {
        "label": "Click & Keri · BBtN · ch9 (Beane playoffs)",
        "detail": "Contention-window framing: marginal win value spikes near a playoff berth.",
    },
    "hole": {
        "label": "Lewis · Moneyball + replacement-level WAR",
        "detail": "Roster construction vs replacement baseline; surplus depth is tradeable.",
    },
    "blend": {
        "label": "McElreath · Statistical Rethinking · ch12-13",
        "detail": "Partial pooling: small 2026 samples shrunk toward the 2025 full-season prior.",
    },
    "farm": {
        "label": "Lindbergh & Sawchik · MVP Machine · ch11 (amateur ball)",
        "detail": "Upper-minors (AAA/AA) performance vs level mean as a near-ready depth proxy.",
    },
}


def blend_weight(games: int) -> float:
    """Weight on 2026-to-date vs the 2025 prior, climbing as the season unfolds.

    Args:
        games: Team games played so far in the current season.

    Returns:
        A weight in ``[0, 0.85]`` applied to the 2026 component.
    """
    return min(games / 120.0, 0.85)


def _games_played(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute(
        "select max(wins + losses) from standings where season = ?", [SEASON]
    ).fetchone()
    return int(row[0]) if row and row[0] else 0


def build_index(conn: duckdb.DuckDBPyConnection, w: float) -> dict:
    """Build the league-index payload: standings, window posture, payroll headroom."""
    rows = conn.execute(
        """
        select s.bref_code, s.wins, s.losses, s.win_pct,
               coalesce(p.total_payroll, 0) as payroll
        from standings s
        left join team_season_payroll_context p
          on p.team_bref = s.bref_code and p.season = s.season
        where s.season = ?
        """,
        [SEASON],
    ).fetchall()

    # division leader (wins, losses) for true games-back
    div_leader: dict[str, tuple[int, int]] = {}
    for code, wins, losses, _pct, _pay in rows:
        div = DIVISIONS.get(code, "?")
        lead = div_leader.get(div)
        if lead is None or wins - losses > lead[0] - lead[1]:
            div_leader[div] = (wins, losses)

    teams = []
    for code, wins, losses, pct, payroll in rows:
        div = DIVISIONS.get(code, "?")
        lw, ll = div_leader[div]
        games_back = max(0.0, round(((lw - wins) + (losses - ll)) / 2, 1))
        posture, _ = window_posture(pct, games_back)
        teams.append(
            {
                "code": code,
                "name": code,
                "division": div,
                "w": wins,
                "l": losses,
                "winPct": round(pct, 3),
                "gamesBack": games_back,
                "windowPosture": posture,
                "payrollCommitted": int(payroll),
                "payrollHeadroom": int(CBT_THRESHOLD_2026 - payroll),
            }
        )
    teams.sort(key=lambda t: (t["division"], -t["winPct"]))
    return {
        "season": SEASON,
        "asOfGames": _games_played(conn),
        "blendWeight": round(w, 3),
        "cbtThreshold": CBT_THRESHOLD_2026,
        "generatedAt": datetime.now(UTC).isoformat(),
        "teams": teams,
    }


def window_posture(win_pct: float, games_back: float) -> tuple[str, str]:
    """Classify a club's contention posture from record + games back.

    Returns:
        ``(posture, rationale)`` where posture is ``buy`` / ``hold`` / ``sell``.
    """
    tag = f"({games_back} GB, {win_pct:.3f})"
    if games_back <= 5 and win_pct >= 0.520:
        return "buy", f"In the hunt {tag} — marginal wins are high-leverage."
    if games_back > 10 and win_pct < 0.480:
        return "sell", f"Out of contention {tag} — sell pending free agents."
    return "hold", f"On the bubble {tag} — direction not yet forced."


def _war_components(
    conn: duckdb.DuckDBPyConnection, season: int
) -> tuple[dict[int, float], dict[int, float]]:
    """Return ``(batting_war, pitching_war)`` maps keyed by mlb_id for a season.

    Splitting the components lets us attribute batting WAR to a player's fielding
    position and pitching WAR to SP/RP independently — which is what makes
    two-way players (Ohtani) and non-hitting pitchers land in the right buckets.
    """
    bat: dict[int, float] = {}
    pit: dict[int, float] = {}
    for mlb_id, war in conn.execute(
        "select mlb_id, sum(war) from bwar_batting where year_id = ? group by mlb_id", [season]
    ).fetchall():
        if mlb_id is not None:
            bat[int(mlb_id)] = war or 0.0
    for mlb_id, war in conn.execute(
        "select mlb_id, sum(war) from bwar_pitching where year_id = ? group by mlb_id", [season]
    ).fetchall():
        if mlb_id is not None:
            pit[int(mlb_id)] = war or 0.0
    return bat, pit


def _pitcher_roles(conn: duckdb.DuckDBPyConnection) -> dict[int, str]:
    """Map mlb_id -> 'SP'/'RP' by games-started share (2026 then 2025 fallback)."""
    roles: dict[int, str] = {}
    for season in (SEASON, PRIOR_SEASON):
        for mlb_id, gs, g in conn.execute(
            "select mlb_id, sum(gs), sum(g) from bwar_pitching where year_id = ? group by mlb_id",
            [season],
        ).fetchall():
            if mlb_id is None or int(mlb_id) in roles or not g:
                continue
            roles[int(mlb_id)] = "SP" if (gs or 0) / g >= 0.5 else "RP"
    return roles


def _all_dev_system_fingerprints(season: int = 2025) -> dict[str, dict[str, Any]]:
    """Compute dev-system fingerprints for every org + low-K targets, keyed by bref_code.

    Called once at export time; result is sliced per-team inside build_team().
    Low-K threshold fixed at 35th percentile to surface the most actionable targets.
    """
    fingerprints = dev_system_mod.org_fingerprints()
    candidates = dev_system_mod.low_k_candidates(season=season, k_pct_rank_max=35.0)

    if fingerprints.empty:
        return {}

    # Rank orgs by avg_k_lift (1 = best K developer)
    fingerprints = fingerprints.sort_values("avg_k_lift", ascending=False).reset_index(drop=True)
    fingerprints["rank"] = range(1, len(fingerprints) + 1)

    result: dict[str, dict[str, Any]] = {}
    for _, row in fingerprints.iterrows():
        bref = str(row["receiver_bref"])
        top_targets: list[dict[str, Any]] = []
        if not candidates.empty:
            for _, p in candidates.head(10).iterrows():
                top_targets.append(
                    {
                        "playerName": str(p["player_name"]),
                        "kPctRank": int(p["k_percent"]),  # type: ignore[arg-type]
                        "whiffRank": int(p["whiff_percent"])  # type: ignore[arg-type]
                        if p.get("whiff_percent") is not None
                        else None,
                        "fbVelo": float(p["fb_velocity"])  # type: ignore[arg-type]  # percentile rank, not mph
                        if p.get("fb_velocity") is not None
                        else None,
                    }
                )
        result[bref] = {
            "avgKLift": round(float(row["avg_k_lift"]), 2),  # type: ignore[arg-type]
            "stdKLift": round(float(row["std_k_lift"]), 2)  # type: ignore[arg-type]
            if row["std_k_lift"] is not None
            else None,
            "nTrades": int(row["n_trades"]),  # type: ignore[arg-type]
            "rank": int(row["rank"]),  # type: ignore[arg-type]
            "nOrgs": len(fingerprints),
            "zKLift": round(float(row["z_k_lift"]), 2),  # type: ignore[arg-type]
            "topTargets": top_targets,
        }
    return result


def _drift_flags_by_team(season: int = 2025) -> dict[str, list[dict[str, Any]]]:
    """Run decline-drift detection and group top flags by current team.

    Returns {bref_code: [{pitcherName, pitchType, driftZ, veloYoY, nPitches}]}.
    Only flags with driftZ >= 1.5 (about 1.5 sigma above cohort mean — sell signal).
    """
    df = decline_drift.flag_drift_pitchers(season=season, min_pitches=100, top_n=80)
    if df.empty:
        return {}

    with connect(read_only=True) as conn:
        roster = conn.execute(
            "SELECT player_id, team_bref FROM team_rosters WHERE season = ? AND roster_type = '40Man'",
            [SEASON],
        ).fetchall()
        if not roster:
            roster = conn.execute(
                "SELECT player_id, team_bref FROM team_rosters WHERE season = ?", [SEASON]
            ).fetchall()

    roster_map: dict[int, str] = {int(pid): str(tbref) for pid, tbref in roster if pid is not None}

    result: dict[str, list[dict[str, Any]]] = {}
    for _, row in df.iterrows():
        drift_z = float(row["drift_z"]) if row["drift_z"] is not None else 0.0  # type: ignore[arg-type]
        if drift_z < 1.5:
            continue
        pid = int(row["player_id"])  # type: ignore[arg-type]
        team = roster_map.get(pid)
        if team is None:
            continue
        flag: dict[str, Any] = {
            "pitcherName": str(row["player_name"]),
            "pitchType": str(row["pitch_type"]),
            "driftZ": round(drift_z, 2),
            "veloYoY": round(float(row["velo_delta_yoy"]), 2)  # type: ignore[arg-type]
            if row["velo_delta_yoy"] is not None
            else None,
            "nPitches": int(row["n_pitches"]),  # type: ignore[arg-type]
        }
        result.setdefault(team, []).append(flag)

    return result


def _all_gm_acceptance() -> dict[str, float]:
    """Fit the GM acceptance model once and score every team's current GM.

    Returns {bref_code: P(accept)}. Returns {} if trade_rumors is unpopulated
    or the model can't train (insufficient weak-labeled examples) — logs a
    warning rather than failing the whole export.
    """
    try:
        gm_acceptance.fit()
    except RuntimeError as exc:
        logger.warning("gm acceptance model unavailable: %s", exc)
        return {}

    with connect(read_only=True) as conn:
        codes = [
            str(row[0])
            for row in conn.execute(
                "SELECT DISTINCT bref_code FROM gm_behavioral_profiles"
            ).fetchall()
        ]

    result: dict[str, float] = {}
    for code in codes:
        p = gm_acceptance.predict_proba_from_profile(code)
        if p is not None:
            result[code] = round(p, 3)
    return result


def _trim_scenario(sc: dict[str, Any]) -> dict[str, Any]:
    """Trim a full scenario payload to the fields consumed by the War Room UI."""

    def _outcome(o: dict[str, Any], with_attribution: bool = False) -> dict[str, Any]:
        cov = o.get("coverage", {})
        result: dict[str, Any] = {
            "mean": o.get("mean"),
            "p5": o.get("p5"),
            "p95": o.get("p95"),
            "pPositive": o.get("p_positive"),
            "coverageGrade": cov.get("grade"),
            "observedFraction": cov.get("observed_fraction"),
        }
        if with_attribution:
            top = o.get("attribution", {}).get("top_contributors", [])[:3]
            result["attribution"] = [
                {
                    "feature": c["feature"],
                    "contribution": c["contribution"],
                    "observed": c["observed"],
                }
                for c in top
            ]
        return result

    return {
        "tradeEventId": sc["trade_event_id"],
        "tradeSeason": sc["trade_season"],
        "receiverBref": sc["receiver_bref"],
        "modelVersion": sc["model_version"],
        "trainEndSeason": sc["train_end_season"],
        "warDelta": _outcome(sc.get("war_delta", {}), with_attribution=True),
        "dollarSurplus": _outcome(sc.get("dollar_surplus", {})),
        "surplusWins": _outcome(sc.get("surplus_wins", {})),
    }


def build_team(
    conn: duckdb.DuckDBPyConnection,
    code: str,
    w: float,
    games: int,
    war: dict[str, tuple[dict[int, float], dict[int, float]]],
    roles: dict[int, str],
    farm_all: dict[str, dict[str, float]],
    index_team: dict,
    dev_fingerprints: dict[str, dict[str, Any]],
    drift_flags: dict[str, list[dict[str, Any]]],
    gm_acceptance_by_team: dict[str, float],
    *,
    with_scenarios: bool = False,
    scenarios_season: int = 2024,
) -> dict:
    """Build one club's War Room payload: context rail + holes board.

    Batting WAR is attributed to a player's primary fielding position and
    pitching WAR to SP/RP, so two-way and pitch-only players bucket correctly.
    """
    pace = 162.0 / games if games else 1.0
    bat26, pit26 = war[str(SEASON)]
    bat25, pit25 = war[str(PRIOR_SEASON)]

    roster = conn.execute(
        """
        select r.player_id, p.primary_position_code
        from team_rosters r
        left join mlb_people p on p.mlb_player_id = r.player_id
        where r.season = ? and r.team_bref = ? and r.roster_type = '40Man'
        """,
        [SEASON, code],
    ).fetchall()
    if not roster:  # fall back if 40Man label differs
        roster = conn.execute(
            "select r.player_id, p.primary_position_code from team_rosters r "
            "left join mlb_people p on p.mlb_player_id = r.player_id "
            "where r.season = ? and r.team_bref = ?",
            [SEASON, code],
        ).fetchall()

    def blend(d26: dict[int, float], d25: dict[int, float], pid: int) -> float:
        return w * (d26.get(pid, 0.0) * pace) + (1 - w) * d25.get(pid, 0.0)

    pos_war: dict[str, float] = {p: 0.0 for p in REPLACEMENT_BASELINE}
    for player_id, pos_code in roster:
        if player_id is None:
            continue
        pid = int(player_id)
        pit_war = blend(pit26, pit25, pid)
        if abs(pit_war) > 0.01:
            pos_war[roles.get(pid, "RP")] += pit_war
        bat_war = blend(bat26, bat25, pid)
        bucket = POSITION_MAP.get(str(pos_code))
        if bucket is not None and abs(bat_war) > 0.01:
            pos_war[bucket] += bat_war

    farm = farm_all.get(code, {})

    holes, surpluses = [], []
    for pos, baseline in REPLACEMENT_BASELINE.items():
        rostered = round(pos_war.get(pos, 0.0), 2)
        farm_w = round(farm.get(pos, 0.0), 2)
        hole_score = round(baseline - (rostered + farm_w), 2)
        entry = {
            "position": pos,
            "rosteredWar": rostered,
            "farmWar": farm_w,
            "replacementBaseline": baseline,
            "holeScore": hole_score,
            "severity": _severity(hole_score, baseline),
            "citation": CITES["hole"],
        }
        if hole_score > 0.5:
            holes.append(entry)
        elif hole_score < -1.0:
            surpluses.append({**entry, "surplus": round(-hole_score, 2)})
    holes.sort(key=lambda h: -h["holeScore"])
    surpluses.sort(key=lambda s: -s["surplus"])

    posture, rationale = window_posture(index_team["winPct"], index_team["gamesBack"])
    expiring = _expiring_contracts(conn, code)

    # GM behavioral context (Phase 3)
    gm_row = conn.execute(
        """
        SELECT gbp.decision_maker, gbp.war_buyer_bias, gbp.avg_age_received,
               gbp.deadline_pct, gbp.n_trades, gbp.trades_per_season,
               ga.archetype, ga.archetype_description
        FROM gm_behavioral_profiles gbp
        LEFT JOIN gm_archetypes ga USING (regime_id)
        WHERE gbp.bref_code = ? AND gbp.regime_end >= 2023
        ORDER BY gbp.regime_end DESC LIMIT 1
        """,
        [code],
    ).fetchone()
    gm_context = None
    if gm_row:
        gm_name, war_bias, avg_age, dl_pct, n_trades, tps, archetype, arch_desc = gm_row
        gm_context = {
            "name": gm_name,
            "archetype": archetype,
            "archetypeDescription": arch_desc,
            "warBuyerBias": round(float(war_bias), 2) if war_bias is not None else None,
            "avgAgeReceived": round(float(avg_age), 1) if avg_age is not None else None,
            "deadlinePct": round(float(dl_pct) * 100, 1) if dl_pct is not None else None,
            "nTrades": int(n_trades) if n_trades is not None else None,
            "tradesPerSeason": round(float(tps), 1) if tps is not None else None,
            "pAccept": gm_acceptance_by_team.get(code),
        }

    return {
        "team": code,
        "context": {
            "standingsLine": f"{index_team['w']}-{index_team['l']} ({index_team['winPct']:.3f}), "
            f"{index_team['gamesBack']} GB · {index_team['division']}",
            "windowPosture": posture,
            "postureRationale": rationale,
            "citation": CITES["window"],
            "payroll": {
                "committed": index_team["payrollCommitted"],
                "cbtThreshold": CBT_THRESHOLD_2026,
                "headroom": index_team["payrollHeadroom"],
            },
            "expiringContracts": expiring,
            "blend": {"w2026": round(w, 3), "w2025": round(1 - w, 3), "citation": CITES["blend"]},
        },
        "holes": holes,
        "surpluses": surpluses,
        "buyLow": [],  # Panel 2 — next pass
        "scenarios": (
            [
                _trim_scenario(s)
                for s in score_historical_scenarios(season=scenarios_season, team_bref=code)
            ]
            if with_scenarios
            else []
        ),
        "lenses": [],  # persona-lens annotations — next pass
        "gmContext": gm_context,
        "devSystem": dev_fingerprints.get(code),
        "driftFlags": drift_flags.get(code, []),
    }


def _affiliations(conn: duckdb.DuckDBPyConnection) -> dict[int, str]:
    """Map MiLB affiliate team_id -> parent club bref_code.

    Fetched once from the MLB Stats API and cached to ``AFFIL_CACHE`` so reruns
    are offline-safe. parentOrgId is an MLB team_id, resolved to bref via teams.
    """
    import json as _json

    if AFFIL_CACHE.exists():
        raw = _json.loads(AFFIL_CACHE.read_text())
    else:
        import httpx

        url = f"https://statsapi.mlb.com/api/v1/teams?sportIds=11,12,13,14&season={SEASON}"
        resp = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        resp.raise_for_status()
        raw = {str(t["id"]): t["parentOrgId"] for t in resp.json()["teams"] if t.get("parentOrgId")}
        AFFIL_CACHE.write_text(_json.dumps(raw))

    bref_by_mlbid = {
        int(mlb_id): bref
        for mlb_id, bref in conn.execute("select mlb_team_id, bref_code from teams").fetchall()
    }
    return {
        int(affil): bref_by_mlbid[int(parent)]
        for affil, parent in raw.items()
        if int(parent) in bref_by_mlbid
    }


def _farm_depth(conn: duckdb.DuckDBPyConnection) -> dict[str, dict[str, float]]:
    """Per-club farm WAR-equiv by position from upper-minors (AAA/AA) performance.

    A labeled heuristic (not modeled WAR): hitters scored on OPS over their level
    mean, pitchers on ERA under their level mean, weighted by proximity to MLB,
    capped per player and per position.
    """
    affil = _affiliations(conn)
    levels = ",".join(str(s) for s in FARM_LEVEL_WEIGHT)
    means = {
        (grp, sid): val
        for grp, sid, val in conn.execute(
            f"""
            select group_name, sport_id,
                   avg(case when group_name='hitting' then ops else era end)
            from milb_player_seasons
            where season = ? and sport_id in ({levels})
              and ((group_name='hitting' and plate_appearances >= ?)
                or (group_name='pitching' and innings_pitched >= ?))
            group by group_name, sport_id
            """,
            [SEASON, FARM_MIN_PA, FARM_MIN_IP],
        ).fetchall()
    }

    out: dict[str, dict[str, float]] = {}

    def credit(parent_id: int, bucket: str, value: float) -> None:
        bref = affil.get(parent_id)
        if not bref or value <= 0:
            return
        team = out.setdefault(bref, {})
        team[bucket] = min(FARM_POS_CAP, team.get(bucket, 0.0) + min(FARM_CAP_PER, value))

    hitters = conn.execute(
        f"""
        select team_id, sport_id, position, ops
        from milb_player_seasons
        where season = ? and group_name = 'hitting'
          and sport_id in ({levels}) and plate_appearances >= ?
        """,
        [SEASON, FARM_MIN_PA],
    ).fetchall()
    for team_id, sid, pos, ops in hitters:
        bucket = MILB_POSITION_MAP.get(pos or "")
        if bucket is None or ops is None:
            continue
        base = means.get(("hitting", sid), 0.74)
        value = (ops - base) * FARM_HIT_K * FARM_LEVEL_WEIGHT[sid]
        credit(team_id, bucket, value)

    pitchers = conn.execute(
        f"""
        select team_id, sport_id, era,
               case when coalesce(games_started,0) >= 0.5 * nullif(games_played,0)
                    then 'SP' else 'RP' end as role
        from milb_player_seasons
        where season = ? and group_name = 'pitching'
          and sport_id in ({levels}) and innings_pitched >= ?
        """,
        [SEASON, FARM_MIN_IP],
    ).fetchall()
    for team_id, sid, era, role in pitchers:
        if era is None:
            continue
        base = means.get(("pitching", sid), 4.50)
        value = max(0.0, (base - era) / base) * FARM_CAP_PER * FARM_LEVEL_WEIGHT[sid]
        credit(team_id, role, value)

    return out


def _severity(hole_score: float, baseline: float) -> str:
    if baseline <= 0:
        return "ok"
    ratio = hole_score / baseline
    if ratio > 0.5:
        return "critical"
    if ratio > 0.25:
        return "warning"
    return "ok"


def _expiring_contracts(conn: duckdb.DuckDBPyConnection, code: str) -> list[dict]:
    rows = conn.execute(
        """
        select player_name, position, cap_hit, status
        from spotrac_player_contracts
        where season = ? and team_bref = ? and cap_hit is not null
        order by cap_hit desc
        limit 6
        """,
        [SEASON, code],
    ).fetchall()
    return [{"player": n, "position": p, "capHit": int(c or 0), "status": s} for n, p, c, s in rows]


def main() -> None:
    """Export the index + per-club War Room JSON snapshots."""
    parser = argparse.ArgumentParser(description="Export War Room JSON snapshots")
    parser.add_argument(
        "--with-scenarios",
        action="store_true",
        help="Populate the scenarios slot with Phase 2 model posteriors (slow first run).",
    )
    parser.add_argument(
        "--scenarios-season",
        type=int,
        default=2024,
        metavar="YEAR",
        help="Which trade season to score for the scenarios slot (default: 2024).",
    )
    parser.add_argument(
        "--warm-cache",
        action="store_true",
        help="Pre-train and cache production fits without running the full export.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.warm_cache:
        from savage_trade_evaluator.modeling.production_fit import warm_cache

        warm_cache()
        logger.info("cache warmed — rerun without --warm-cache to export")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with connect(read_only=True) as conn:
        games = _games_played(conn)
        w = blend_weight(games)
        logger.info("season=%s games=%s blend_w=%.3f", SEASON, games, w)

        index = build_index(conn, w)
        (OUT_DIR / "index.json").write_text(json.dumps(index, indent=2))
        logger.info("wrote index.json (%d teams)", len(index["teams"]))

        war = {
            str(SEASON): _war_components(conn, SEASON),
            str(PRIOR_SEASON): _war_components(conn, PRIOR_SEASON),
        }
        roles = _pitcher_roles(conn)
        farm_all = _farm_depth(conn)
        logger.info("farm depth computed for %d clubs", len(farm_all))
        index_by_code = {t["code"]: t for t in index["teams"]}

        dev_fingerprints = _all_dev_system_fingerprints(season=2025)
        logger.info("dev-system fingerprints computed for %d orgs", len(dev_fingerprints))

        drift_flags = _drift_flags_by_team(season=2025)
        logger.info("drift flags computed for %d teams", len(drift_flags))

        gm_acceptance_by_team = _all_gm_acceptance()
        logger.info("gm acceptance scored for %d teams", len(gm_acceptance_by_team))

        for t in index["teams"]:
            payload = build_team(
                conn,
                t["code"],
                w,
                games,
                war,
                roles,
                farm_all,
                index_by_code[t["code"]],
                dev_fingerprints,
                drift_flags,
                gm_acceptance_by_team,
                with_scenarios=args.with_scenarios,
                scenarios_season=args.scenarios_season,
            )
            (OUT_DIR / f"{t['code']}.json").write_text(json.dumps(payload, indent=2))
        logger.info("wrote %d team files to %s", len(index["teams"]), OUT_DIR)
        if args.with_scenarios:
            logger.info("scenarios slot populated for season=%d", args.scenarios_season)


if __name__ == "__main__":
    main()
