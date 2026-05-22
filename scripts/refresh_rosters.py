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


_PARTIAL_SEASON_THRESHOLD = 100  # max-g below this → treat season as in-progress
_WAR_WEIGHTS = {0: 0.50, 1: 0.30, 2: 0.20}  # offset from most-recent completed season


def _fetch_war_history(conn: duckdb.DuckDBPyConnection, ids: list[int]) -> dict[int, dict[str, Any]]:
    """Compute war_3yr_wtd / war_current_pace / war_trend for each player.

    Excludes the current partial season from the weighted baseline, then
    annualises it separately as war_current_pace so the trend comparison is
    against full-season equivalents.
    """
    if not ids:
        return {}
    # Detect partial season
    row = conn.execute("""
        WITH ym AS (SELECT year_id, MAX(g) AS mg FROM
            (SELECT year_id, g FROM bwar_batting
             UNION ALL SELECT year_id, g FROM bwar_pitching)
        GROUP BY year_id)
        SELECT year_id, mg FROM ym ORDER BY year_id DESC LIMIT 1
    """).fetchone()
    partial_year: int | None = None
    pace_factor: float | None = None
    if row and float(row[1]) < _PARTIAL_SEASON_THRESHOLD:
        partial_year = int(row[0])
        pace_factor = 162.0 / float(row[1])

    placeholders = ",".join(["?"] * len(ids))
    year_filter = f"WHERE year_id != {partial_year}" if partial_year else ""
    rows = conn.execute(
        f"""
        WITH seasons AS (
            SELECT mlb_id, year_id, SUM(war) AS war
            FROM (
                SELECT mlb_id, year_id, war FROM bwar_batting  WHERE mlb_id IN ({placeholders})
                UNION ALL
                SELECT mlb_id, year_id, war FROM bwar_pitching WHERE mlb_id IN ({placeholders})
            ) GROUP BY mlb_id, year_id
        ),
        completed AS (SELECT mlb_id, year_id, war FROM seasons {year_filter}),
        latest AS (SELECT mlb_id, MAX(year_id) AS last_y FROM completed GROUP BY mlb_id),
        ranked AS (
            SELECT c.mlb_id, c.year_id, c.war, (l.last_y - c.year_id) AS off
            FROM completed c JOIN latest l ON l.mlb_id = c.mlb_id
            WHERE c.year_id >= l.last_y - 2
        )
        SELECT mlb_id, off, war FROM ranked ORDER BY mlb_id, off
        """,
        ids + ids,
    ).fetchall()

    partial_war_map: dict[int, float] = {}
    if partial_year:
        p_rows = conn.execute(
            f"""SELECT mlb_id, SUM(war) FROM (
                SELECT mlb_id, war FROM bwar_batting  WHERE mlb_id IN ({placeholders}) AND year_id={partial_year}
                UNION ALL
                SELECT mlb_id, war FROM bwar_pitching WHERE mlb_id IN ({placeholders}) AND year_id={partial_year}
            ) GROUP BY mlb_id""",
            ids + ids,
        ).fetchall()
        partial_war_map = {int(r[0]): float(r[1]) if r[1] is not None else 0.0 for r in p_rows}

    by_id: dict[int, list[tuple[int, float]]] = {}
    for mlb_id, off, war in rows:
        by_id.setdefault(int(mlb_id), []).append((int(off), float(war) if war is not None else 0.0))

    out: dict[int, dict[str, Any]] = {}
    for mlb_id in set(by_id) | set(partial_war_map):
        entries = by_id.get(mlb_id, [])
        total_w = sum(_WAR_WEIGHTS.get(o, 0.0) for o, _ in entries)
        wtd = (
            round(sum(_WAR_WEIGHTS.get(o, 0.0) * w for o, w in entries) / total_w, 3)
            if total_w > 0 else None
        )
        pace = (
            round(partial_war_map[mlb_id] * pace_factor, 3)
            if (mlb_id in partial_war_map and pace_factor is not None) else None
        )
        if pace is not None and wtd is not None:
            trend: float | None = round(pace - wtd, 3)
        elif wtd is not None:
            last = partial_war_map.get(mlb_id) or next((w for o, w in entries if o == 0), None)
            trend = round(last - wtd, 3) if last is not None else None
        else:
            trend = None
        out[mlb_id] = {
            "war_3yr_wtd": wtd,
            "war_current_pace": pace,
            "war_trend": trend,
            "war_years": len(entries),
        }
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
    war_history_by_id: dict[int, dict[str, Any]] = {}
    spotrac_by_id: dict[int, dict[str, Any]] = {}
    awards_by_id: dict[int, dict[str, Any]] = {}
    if db_path:
        logger.info("Joining bWAR + Spotrac contracts + awards from %s", db_path)
        with duckdb.connect(str(db_path), read_only=True) as conn:
            war_by_id = fetch_recent_war(conn, all_ids)
            war_history_by_id = _fetch_war_history(conn, all_ids)
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
            wh = war_history_by_id.get(person_id, {})
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
                    # Multi-year WAR baseline (see enrich_player_war.py for methodology)
                    "war_3yr_wtd": wh.get("war_3yr_wtd"),
                    "war_current_pace": wh.get("war_current_pace"),
                    "war_trend": wh.get("war_trend"),
                    "war_years": wh.get("war_years", 0),
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
