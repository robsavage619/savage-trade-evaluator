"""Pull live 40-man rosters for all 30 MLB clubs from MLB Stats API and write
a compact ``current_players.json`` seed the frontend consumes.

Joins live roster data (status, jersey, position) with recent bWAR / salary
from the local DuckDB (most recent season we have ingested) so each player
card carries production context.

Run:
    uv run python scripts/refresh_rosters.py
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
SEED_DIR = PROJECT_ROOT / "frontend" / "src" / "data" / "seed"
OUT_PATH = SEED_DIR / "current_players.json"

DB_CANDIDATES = [
    Path("/tmp/ste_trades_snapshot.db"),
    PROJECT_ROOT / "data" / "duckdb" / "trades.db",
    Path(
        "/Users/robsavage/Projects/savage-trade-evaluator/.claude/worktrees/gallant-cerf-24bd10/data/duckdb/trades.db"
    ),
]

MLB_BASE = "https://statsapi.mlb.com/api/v1"
HEADERS = {"User-Agent": "savage-trade-evaluator/0.1"}

# bref_code → mlb team_id (mirrors frontend lib/format.ts)
TEAM_ROSTER: list[tuple[str, int, str]] = [
    ("ARI", 109, "Arizona Diamondbacks"),
    ("ATL", 144, "Atlanta Braves"),
    ("BAL", 110, "Baltimore Orioles"),
    ("BOS", 111, "Boston Red Sox"),
    ("CHC", 112, "Chicago Cubs"),
    ("CHW", 145, "Chicago White Sox"),
    ("CIN", 113, "Cincinnati Reds"),
    ("CLE", 114, "Cleveland Guardians"),
    ("COL", 115, "Colorado Rockies"),
    ("DET", 116, "Detroit Tigers"),
    ("HOU", 117, "Houston Astros"),
    ("KCR", 118, "Kansas City Royals"),
    ("LAA", 108, "Los Angeles Angels"),
    ("LAD", 119, "Los Angeles Dodgers"),
    ("MIA", 146, "Miami Marlins"),
    ("MIL", 158, "Milwaukee Brewers"),
    ("MIN", 142, "Minnesota Twins"),
    ("NYM", 121, "New York Mets"),
    ("NYY", 147, "New York Yankees"),
    ("OAK", 133, "Athletics"),
    ("PHI", 143, "Philadelphia Phillies"),
    ("PIT", 134, "Pittsburgh Pirates"),
    ("SDP", 135, "San Diego Padres"),
    ("SEA", 136, "Seattle Mariners"),
    ("SFG", 137, "San Francisco Giants"),
    ("STL", 138, "St. Louis Cardinals"),
    ("TBR", 139, "Tampa Bay Rays"),
    ("TEX", 140, "Texas Rangers"),
    ("TOR", 141, "Toronto Blue Jays"),
    ("WSN", 120, "Washington Nationals"),
]


def _http_json(url: str, retries: int = 3) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    assert last_err is not None
    raise last_err


def fetch_roster(team_id: int) -> list[dict[str, Any]]:
    """40-man roster with status, jersey, position abbreviation."""
    data = _http_json(f"{MLB_BASE}/teams/{team_id}/roster?rosterType=40Man")
    return data.get("roster", [])


def fetch_people(ids: list[int]) -> list[dict[str, Any]]:
    """Batched person fetch — MLB API supports comma-separated personIds."""
    if not ids:
        return []
    # Chunk to keep URL length safe
    out: list[dict[str, Any]] = []
    CHUNK = 50
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i : i + CHUNK]
        url = f"{MLB_BASE}/people?personIds={','.join(map(str, chunk))}"
        data = _http_json(url)
        out.extend(data.get("people", []))
    return out


def age_on(birth: str | None, on: date) -> int | None:
    if not birth:
        return None
    try:
        b = datetime.fromisoformat(birth).date()
    except ValueError:
        return None
    age = on.year - b.year - ((on.month, on.day) < (b.month, b.day))
    return age


def _resolve_db() -> Path | None:
    for c in DB_CANDIDATES:
        if c.exists():
            return c
    return None


def fetch_spotrac(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Latest available Spotrac contract row per player."""
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY mlb_player_id ORDER BY season DESC) AS rn
            FROM spotrac_player_contracts
            WHERE mlb_player_id IN ({placeholders})
        )
        SELECT mlb_player_id, season, team_bref, status, service_time,
               acquired_method, base_salary, cap_hit, signing_bonus, position
        FROM ranked WHERE rn = 1
        """,
        ids,
    ).fetchall()
    return {
        int(r[0]): {
            "spotrac_season": int(r[1]) if r[1] is not None else None,
            "contract_team": r[2],
            "contract_status": r[3] or None,
            "service_time": float(r[4]) if r[4] is not None else None,
            "acquired_method": r[5] or None,
            "base_salary": int(r[6]) if r[6] is not None else None,
            "cap_hit": int(r[7]) if r[7] is not None else None,
            "signing_bonus": int(r[8]) if r[8] is not None else None,
            "spotrac_position": r[9] or None,
        }
        for r in rows
    }


def fetch_awards(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Per-player major-awards summary: All-Star × n, MVP × n, Cy × n, Silver Slugger, Gold Glove."""
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"""
        SELECT player_id, award_name, COUNT(*) AS n
        FROM mlb_awards
        WHERE player_id IN ({placeholders})
        GROUP BY player_id, award_name
        """,
        ids,
    ).fetchall()
    out: dict[int, dict[str, Any]] = {}
    for pid, award_name, n in rows:
        pid = int(pid)
        if pid not in out:
            out[pid] = {"all_star": 0, "mvp": 0, "cy_young": 0, "silver_slugger": 0, "gold_glove": 0, "rookie_of_year": 0, "total": 0}
        award_lc = (award_name or "").lower()
        if "all-star" in award_lc or "all star" in award_lc:
            out[pid]["all_star"] += int(n)
        elif "mvp" in award_lc:
            out[pid]["mvp"] += int(n)
        elif "cy young" in award_lc:
            out[pid]["cy_young"] += int(n)
        elif "silver slugger" in award_lc:
            out[pid]["silver_slugger"] += int(n)
        elif "gold glove" in award_lc:
            out[pid]["gold_glove"] += int(n)
        elif "rookie of the year" in award_lc:
            out[pid]["rookie_of_year"] += int(n)
        out[pid]["total"] += int(n)
    return out


def fetch_recent_war(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, dict[str, Any]]:
    """For each player, last-season WAR + salary across batting/pitching."""
    if not ids:
        return {}
    placeholders = ",".join(["?"] * len(ids))
    rows = conn.execute(
        f"""
        WITH all_seasons AS (
            SELECT mlb_id, year_id, team_id, war, salary, 'bat' AS role FROM bwar_batting
             WHERE mlb_id IN ({placeholders})
            UNION ALL
            SELECT mlb_id, year_id, team_id, war, salary, 'pit' AS role FROM bwar_pitching
             WHERE mlb_id IN ({placeholders})
        ),
        latest AS (
            SELECT mlb_id, MAX(year_id) AS last_year
            FROM all_seasons GROUP BY mlb_id
        )
        SELECT a.mlb_id, a.year_id, SUM(a.war) AS war, MAX(a.salary) AS salary
        FROM all_seasons a JOIN latest l ON l.mlb_id = a.mlb_id AND a.year_id = l.last_year
        GROUP BY a.mlb_id, a.year_id
        """,
        ids + ids,
    ).fetchall()
    return {
        int(r[0]): {"last_year": int(r[1]), "last_war": float(r[2]) if r[2] is not None else None, "last_salary": int(r[3]) if r[3] is not None else None}
        for r in rows
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    today = date.today()

    # Parallel roster fetch
    logger.info("Pulling 40-man rosters for 30 clubs from MLB Stats API…")
    team_rosters: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        future_to_team = {
            ex.submit(fetch_roster, team_id): (bref, team_id, name) for bref, team_id, name in TEAM_ROSTER
        }
        for fut in as_completed(future_to_team):
            bref, team_id, name = future_to_team[fut]
            try:
                team_rosters[bref] = fut.result()
            except Exception as e:
                logger.warning("roster fetch failed for %s: %s", bref, e)
                team_rosters[bref] = []

    # Collect all player ids
    all_ids: list[int] = []
    for roster in team_rosters.values():
        for entry in roster:
            person = entry.get("person", {})
            pid = person.get("id")
            if pid:
                all_ids.append(int(pid))

    logger.info("Fetching bio data for %d players…", len(all_ids))
    people = fetch_people(all_ids)
    by_id: dict[int, dict[str, Any]] = {int(p["id"]): p for p in people}

    # Join with bWAR + Spotrac + awards
    db_path = _resolve_db()
    war_by_id: dict[int, dict[str, Any]] = {}
    spotrac_by_id: dict[int, dict[str, Any]] = {}
    awards_by_id: dict[int, dict[str, Any]] = {}
    if db_path:
        logger.info("Joining bWAR + Spotrac contracts + awards from %s", db_path)
        with duckdb.connect(str(db_path), read_only=True) as conn:
            war_by_id = fetch_recent_war(conn, all_ids)
            spotrac_by_id = fetch_spotrac(conn, all_ids)
            awards_by_id = fetch_awards(conn, all_ids)
    else:
        logger.warning("No local DuckDB found — skipping joins.")

    # Compose final payload
    teams_payload: list[dict[str, Any]] = []
    for bref, team_id, name in TEAM_ROSTER:
        players: list[dict[str, Any]] = []
        for entry in team_rosters.get(bref, []):
            person_id = int(entry.get("person", {}).get("id", 0))
            if not person_id:
                continue
            bio = by_id.get(person_id, {})
            pos = entry.get("position", {})
            war = war_by_id.get(person_id, {})
            players.append(
                {
                    "mlb_player_id": person_id,
                    "name": entry.get("person", {}).get("fullName"),
                    "jersey": entry.get("jerseyNumber"),
                    "position_code": pos.get("code"),
                    "position_abbr": pos.get("abbreviation"),
                    "position_name": pos.get("name"),
                    "status_code": entry.get("status", {}).get("code"),
                    "status_desc": entry.get("status", {}).get("description"),
                    "note": entry.get("note"),
                    "birth_date": bio.get("birthDate"),
                    "age": age_on(bio.get("birthDate"), today),
                    "birth_country": bio.get("birthCountry"),
                    "height": bio.get("height"),
                    "weight": bio.get("weight"),
                    "bat_side": bio.get("batSide", {}).get("code") if bio.get("batSide") else None,
                    "pitch_hand": bio.get("pitchHand", {}).get("code") if bio.get("pitchHand") else None,
                    "mlb_debut_date": bio.get("mlbDebutDate"),
                    "last_year": war.get("last_year"),
                    "last_war": war.get("last_war"),
                    "last_salary": war.get("last_salary"),
                    # Spotrac contract overlay (most recent ingested season)
                    "spotrac_season": spotrac_by_id.get(person_id, {}).get("spotrac_season"),
                    "contract_status": spotrac_by_id.get(person_id, {}).get("contract_status"),
                    "service_time": spotrac_by_id.get(person_id, {}).get("service_time"),
                    "acquired_method": spotrac_by_id.get(person_id, {}).get("acquired_method"),
                    "cap_hit": spotrac_by_id.get(person_id, {}).get("cap_hit"),
                    "base_salary_spotrac": spotrac_by_id.get(person_id, {}).get("base_salary"),
                    # Awards summary
                    "awards": awards_by_id.get(person_id),
                }
            )
        teams_payload.append(
            {
                "bref": bref,
                "mlb_team_id": team_id,
                "name": name,
                "roster_count": len(players),
                "players": players,
            }
        )

    out = {
        "refreshed_at": datetime.now(tz=timezone.utc).isoformat(),
        "season_used_for_war": max((p.get("last_year") for t in teams_payload for p in t["players"] if p.get("last_year")), default=None),
        "team_count": len(teams_payload),
        "player_count": sum(t["roster_count"] for t in teams_payload),
        "teams": teams_payload,
    }

    SEED_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    logger.info("wrote %s — %d teams, %d players", OUT_PATH.relative_to(PROJECT_ROOT), out["team_count"], out["player_count"])


if __name__ == "__main__":
    main()
