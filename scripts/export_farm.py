"""Export MiLB farm rosters grouped by parent MLB org.

Joins the new ``milb_player_season_aggregate`` + ``milb_player_seasons`` tables
(schema v20) with a live MLB Stats API call to resolve ``team_id`` →
``parentOrgId``. Writes ``frontend/src/data/seed/current_farm.json`` keyed by
the parent club's bref code; each bucket carries the org's prospects grouped
by level (AAA / AA / A+ / A).

Run:
    uv run python scripts/export_farm.py
"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false

from __future__ import annotations

import json
import logging
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = PROJECT_ROOT / "frontend" / "src" / "data" / "seed" / "current_farm.json"

DB_CANDIDATES = [
    Path("/tmp/ste_trades_snapshot.db"),
    PROJECT_ROOT / "data" / "duckdb" / "trades.db",
    Path(
        "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db"
    ),
]

LEVEL_BY_SPORT: dict[int, str] = {
    11: "AAA",
    12: "AA",
    13: "A+",
    14: "A",
    16: "R",
}

# bref ↔ parent MLB team_id (mirrors lib/format.ts on the frontend)
MLB_BY_BREF: dict[str, int] = {
    "ARI": 109, "ATL": 144, "BAL": 110, "BOS": 111, "CHC": 112, "CHW": 145, "CIN": 113,
    "CLE": 114, "COL": 115, "DET": 116, "HOU": 117, "KCR": 118, "LAA": 108, "LAD": 119,
    "MIA": 146, "MIL": 158, "MIN": 142, "NYM": 121, "NYY": 147, "OAK": 133, "PHI": 143,
    "PIT": 134, "SDP": 135, "SEA": 136, "SFG": 137, "STL": 138, "TBR": 139, "TEX": 140,
    "TOR": 141, "WSN": 120,
}
BREF_BY_MLB_ID: dict[int, str] = {v: k for k, v in MLB_BY_BREF.items()}


def _resolve_db() -> Path:
    for c in DB_CANDIDATES:
        if c.exists():
            return c
    msg = f"No DuckDB found in {DB_CANDIDATES}"
    raise FileNotFoundError(msg)


CURRENT_SEASON = 2026


def fetch_team_parent_map(season: int) -> dict[int, dict[str, Any]]:
    """Returns minor_team_id -> {parent_bref, level, team_name}.

    Uses the live MLB Stats API affiliate alignment, not the stale 2024
    affiliations that produced the data. This is the authority for "where is
    this player now."
    """
    url = f"https://statsapi.mlb.com/api/v1/teams?sportIds=11,12,13,14,16&season={season}"
    req = urllib.request.Request(url, headers={"User-Agent": "savage-trade-evaluator/0.1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for t in data.get("teams", []):
        sport_id = (t.get("sport") or {}).get("id")
        parent_mlb_id = t.get("parentOrgId")
        parent_bref = BREF_BY_MLB_ID.get(parent_mlb_id)
        if not parent_bref:
            continue
        out[int(t["id"])] = {
            "parent_bref": parent_bref,
            "level": LEVEL_BY_SPORT.get(sport_id, "?"),
            "sport_id": sport_id,
            "team_name": t.get("name"),
            "team_abbrev": t.get("abbreviation"),
        }
    return out


def fetch_current_team_chunk(ids: list[int]) -> dict[int, dict[str, Any]]:
    """Bulk-fetch currentTeam for up to 50 player ids."""
    url = f"https://statsapi.mlb.com/api/v1/people?personIds={','.join(map(str, ids))}&hydrate=currentTeam"
    req = urllib.request.Request(url, headers={"User-Agent": "savage-trade-evaluator/0.1"})
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    else:
        raise last_err if last_err else RuntimeError("currentTeam fetch failed")
    out: dict[int, dict[str, Any]] = {}
    for p in data.get("people", []):
        ct = p.get("currentTeam") or {}
        out[int(p["id"])] = {
            "current_team_id": ct.get("id"),
            "current_team_name": ct.get("name"),
            "current_parent_org_id": ct.get("parentOrgId"),
            "current_full_name": p.get("fullName"),
        }
    return out


def fetch_all_current_teams(ids: list[int]) -> dict[int, dict[str, Any]]:
    """Parallel-chunked bulk fetch of currentTeam for every farm player id."""
    chunks = [ids[i : i + 50] for i in range(0, len(ids), 50)]
    out: dict[int, dict[str, Any]] = {}
    completed = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_current_team_chunk, c): c for c in chunks}
        for fut in as_completed(futures):
            try:
                out.update(fut.result())
            except Exception as e:
                logger.warning("currentTeam chunk failed: %s", e)
            completed += 1
            if completed % 20 == 0:
                logger.info("  currentTeam: %d/%d chunks", completed, len(chunks))
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    db_path = _resolve_db()

    with duckdb.connect(str(db_path), read_only=True) as conn:
        latest_season = conn.execute("SELECT MAX(season) FROM milb_player_seasons").fetchone()[0]
        logger.info("opening %s · latest MiLB season=%s", db_path, latest_season)

        # Pull CURRENT (2026) affiliate map — this is the authority for where
        # each minor-league team belongs in the org tree right now.
        logger.info("fetching live 2026 team-affiliate map…")
        team_map = fetch_team_parent_map(CURRENT_SEASON)
        # Fall back to the 2024 map for any team_ids that no longer exist in 2026
        legacy_map = fetch_team_parent_map(int(latest_season))
        logger.info("mapped %d minor-league teams (current) + %d legacy fallback", len(team_map), len(legacy_map))

        # Primary team per player this season (most PA/IP). Use the detail table
        # to pick the team they spent the most playing time with; merge with the
        # PA-weighted aggregate for that season.
        logger.info("pulling per-player primary team + aggregate stats…")
        rows = conn.execute(
            """
            WITH primary_team AS (
                SELECT mlb_player_id,
                       group_name,
                       team_id,
                       team_name,
                       position,
                       age,
                       ROW_NUMBER() OVER (
                           PARTITION BY mlb_player_id, group_name
                           ORDER BY COALESCE(plate_appearances, 0) + COALESCE(innings_pitched, 0) DESC
                       ) AS rn
                FROM milb_player_seasons
                WHERE season = ?
            ),
            named AS (
                SELECT DISTINCT mlb_player_id, player_name
                FROM milb_player_seasons
                WHERE season = ? AND player_name IS NOT NULL
            )
            SELECT a.mlb_player_id,
                   a.group_name,
                   a.top_sport_id,
                   a.pa, a.ab, a.hits, a.hr, a.k, a.bb, a.ops_pa_weighted, a.age,
                   a.ip, a.era_ip_weighted,
                   pt.team_id, pt.team_name, pt.position,
                   n.player_name
            FROM milb_player_season_aggregate a
            JOIN primary_team pt ON pt.mlb_player_id = a.mlb_player_id AND pt.group_name = a.group_name AND pt.rn = 1
            LEFT JOIN named n ON n.mlb_player_id = a.mlb_player_id
            WHERE a.season = ?
            """,
            [latest_season, latest_season, latest_season],
        ).fetchall()
        cols = [
            "mlb_player_id", "group_name", "top_sport_id", "pa", "ab", "hits", "hr", "k", "bb",
            "ops_pa_weighted", "age", "ip", "era_ip_weighted",
            "team_id", "team_name", "position", "player_name",
        ]

        # Person bio supplement (height/weight/hand etc.)
        ids = list({int(r[0]) for r in rows})
        placeholders = ",".join(["?"] * len(ids))
        bio = {
            int(r[0]): r
            for r in conn.execute(
                f"SELECT mlb_player_id, primary_position_name, primary_position_code, "
                f"primary_position_type, bat_side, pitch_hand, height_inches, "
                f"weight_lbs, birth_country FROM mlb_people WHERE mlb_player_id IN ({placeholders})",
                ids,
            ).fetchall()
        } if ids else {}

    # Fetch CURRENT team for every farm player — single source of truth for
    # parent-org assignment (handles offseason trades, releases, promotions).
    all_player_ids = sorted({int(r[cols.index("mlb_player_id")]) for r in rows})
    logger.info("fetching live currentTeam for %d farm players from MLB Stats API…", len(all_player_ids))
    current_team_by_id = fetch_all_current_teams(all_player_ids)
    logger.info("resolved currentTeam for %d/%d players", len(current_team_by_id), len(all_player_ids))

    # Distribute rows per parent org — preferring CURRENT alignment
    buckets: dict[str, dict[str, list[dict[str, Any]]]] = {bref: {"MLB": [], "AAA": [], "AA": [], "A+": [], "A": [], "R": []} for bref in MLB_BY_BREF}
    unmatched = 0
    moved_count = 0

    for r in rows:
        record = dict(zip(cols, r, strict=True))
        pid = int(record["mlb_player_id"])
        b = bio.get(pid)
        is_pitcher = (record["group_name"] == "pitching")

        # Resolve current parent org from live API
        ct = current_team_by_id.get(pid) or {}
        current_team_id = ct.get("current_team_id")
        current_parent_mlb_id = ct.get("current_parent_org_id")
        current_team_name = ct.get("current_team_name")

        current_parent_bref: str | None = None
        current_level: str | None = None
        current_team_meta: dict[str, Any] | None = None

        if current_team_id is not None:
            # Case A: on a MLB 40-man — currentTeam.id is the parent MLB id itself
            if int(current_team_id) in BREF_BY_MLB_ID:
                current_parent_bref = BREF_BY_MLB_ID[int(current_team_id)]
                current_level = "MLB"
                current_team_meta = {"team_name": current_team_name, "team_abbrev": None}
            else:
                # Case B: on a minor-league team — look it up in the live affiliate map
                meta_live = team_map.get(int(current_team_id)) or legacy_map.get(int(current_team_id))
                if meta_live:
                    current_parent_bref = meta_live["parent_bref"]
                    current_level = meta_live["level"]
                    current_team_meta = meta_live
                elif current_parent_mlb_id is not None and int(current_parent_mlb_id) in BREF_BY_MLB_ID:
                    current_parent_bref = BREF_BY_MLB_ID[int(current_parent_mlb_id)]
                    current_level = "?"
                    current_team_meta = {"team_name": current_team_name, "team_abbrev": None}

        # Stale 2024 affiliation (used for "moved since" detection)
        team_id_2024 = record["team_id"]
        meta_2024 = team_map.get(int(team_id_2024)) if team_id_2024 is not None else None
        if not meta_2024:
            meta_2024 = legacy_map.get(int(team_id_2024)) if team_id_2024 is not None else None
        parent_2024 = meta_2024.get("parent_bref") if meta_2024 else None

        if current_parent_bref is None:
            # No current affiliation — free agent / released / DFA'd
            unmatched += 1
            continue

        if current_level not in buckets[current_parent_bref]:
            buckets[current_parent_bref].setdefault(current_level, [])

        moved = parent_2024 is not None and parent_2024 != current_parent_bref
        if moved:
            moved_count += 1

        player = {
            "mlb_player_id": pid,
            "name": record["player_name"] or ct.get("current_full_name"),
            "age": int(record["age"]) if record["age"] is not None else None,
            "position_abbr": b[3] if b else record["position"],
            "position_name": b[1] if b else None,
            "position_code": b[2] if b else None,
            "bat_side": b[4] if b else None,
            "pitch_hand": b[5] if b else None,
            "height_inches": b[6] if b else None,
            "weight_lbs": b[7] if b else None,
            "birth_country": b[8] if b else None,
            "is_pitcher": is_pitcher,
            "team_id": int(current_team_id) if current_team_id is not None else None,
            "team_name": (current_team_meta or {}).get("team_name") or current_team_name,
            "team_abbrev": (current_team_meta or {}).get("team_abbrev"),
            "level": current_level,
            "former_team_name": meta_2024.get("team_name") if meta_2024 else record.get("team_name"),
            "former_parent": parent_2024,
            "moved_since_2024": moved,
            "top_sport_id": int(record["top_sport_id"]) if record["top_sport_id"] is not None else None,
            "top_level": LEVEL_BY_SPORT.get(int(record["top_sport_id"]), current_level) if record["top_sport_id"] is not None else current_level,
            # Hitting (2024 stats)
            "pa": record["pa"], "ab": record["ab"], "hits": record["hits"],
            "hr": record["hr"], "bb": record["bb"], "k": record["k"],
            "ops_pa_weighted": record["ops_pa_weighted"],
            # Pitching (2024 stats)
            "ip": record["ip"], "era_ip_weighted": record["era_ip_weighted"],
        }
        buckets[current_parent_bref][current_level].append(player)

    # Sort each level: hitters by OPS desc, pitchers by ERA asc (with min IP)
    LEVEL_ORDER = ["MLB", "AAA", "AA", "A+", "A", "R"]
    teams_out: list[dict[str, Any]] = []
    for bref in sorted(MLB_BY_BREF):
        levels: dict[str, list[dict[str, Any]]] = {}
        total = 0
        for lv in LEVEL_ORDER:
            arr = buckets[bref].get(lv, [])
            # Sort: prioritize position (pitchers separate), then quality
            hitters = [p for p in arr if not p["is_pitcher"]]
            pitchers = [p for p in arr if p["is_pitcher"]]
            hitters.sort(key=lambda p: -(p.get("ops_pa_weighted") or 0))
            pitchers.sort(key=lambda p: (p.get("era_ip_weighted") or 99))
            merged = hitters + pitchers
            levels[lv] = merged
            total += len(merged)
        teams_out.append({"bref": bref, "season": int(latest_season), "total_players": total, "levels": levels})

    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "season": int(latest_season),
        "team_count": len(teams_out),
        "player_count": sum(t["total_players"] for t in teams_out),
        "unmatched_count": unmatched,
        "teams": {t["bref"]: t for t in teams_out},
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, separators=(",", ":"), default=str))
    logger.info(
        "wrote %s — %d teams, %d players, %d unmatched, %d re-bucketed (moved since 2024) · %.1f KB",
        OUT_PATH.relative_to(PROJECT_ROOT),
        payload["team_count"],
        payload["player_count"],
        unmatched,
        moved_count,
        OUT_PATH.stat().st_size / 1024,
    )


if __name__ == "__main__":
    main()
