"""Ingest MLB player contract / salary data from Spotrac.

Spotrac (spotrac.com/mlb) publishes per-team payroll pages with active +
dead-money + injured-list breakdowns. The HTML is server-rendered with
clean ``<table id="table_active">`` / ``table_dead`` / ``table_injured``
structures — fully scrapeable with a regex parser, no JS required.

URL patterns confirmed working:
- Current season: ``spotrac.com/mlb/<team-slug>/payroll/``
- Historical:     ``spotrac.com/mlb/<team-slug>/payroll/_/year/<YYYY>``

Per-player row structure (9 columns in the active table):
  player_name | position | service_time | acquired_method | status |
  base_salary | cap_hit | signing_bonus | incentives

Plus a player link: ``/mlb/player/_/id/<spotrac_id>/<slug>``.

Player-to-MLBAM-ID mapping is done via name match against the
``mlb_people`` table (96.6% coverage). Mismatches get left with NULL
mlb_player_id; they can still be aggregated by name and team.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any

import httpx

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)
SOURCE = "spotrac"
RATE_LIMIT_SECONDS = 1.5  # polite — Spotrac is a small business

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Map our bref_code → Spotrac team slug. All 30 current franchises.
TEAM_SLUG_BY_BREF: dict[str, str] = {
    "ARI": "arizona-diamondbacks",
    "ATL": "atlanta-braves",
    "BAL": "baltimore-orioles",
    "BOS": "boston-red-sox",
    "CHC": "chicago-cubs",
    "CHW": "chicago-white-sox",
    "CIN": "cincinnati-reds",
    "CLE": "cleveland-guardians",
    "COL": "colorado-rockies",
    "DET": "detroit-tigers",
    "HOU": "houston-astros",
    "KCR": "kansas-city-royals",
    "LAA": "los-angeles-angels",
    "LAD": "los-angeles-dodgers",
    "MIA": "miami-marlins",
    "MIL": "milwaukee-brewers",
    "MIN": "minnesota-twins",
    "NYM": "new-york-mets",
    "NYY": "new-york-yankees",
    "OAK": "oakland-athletics",
    "PHI": "philadelphia-phillies",
    "PIT": "pittsburgh-pirates",
    "SDP": "san-diego-padres",
    "SEA": "seattle-mariners",
    "SFG": "san-francisco-giants",
    "STL": "st-louis-cardinals",
    "TBR": "tampa-bay-rays",
    "TEX": "texas-rangers",
    "TOR": "toronto-blue-jays",
    "WSN": "washington-nationals",
}

PAYROLL_URL_CURRENT = "https://www.spotrac.com/mlb/{slug}/payroll/"
PAYROLL_URL_HISTORICAL = "https://www.spotrac.com/mlb/{slug}/payroll/_/year/{year}"

# Spotrac money string patterns
MONEY_RE = re.compile(r"\$?([\d,]+(?:\.\d+)?)")
# Player link inside a table cell
PLAYER_LINK_RE = re.compile(r'href="https://www\.spotrac\.com/mlb/player/_/id/(\d+)/([a-z0-9-]+)"')
# Row + cell extraction
ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")


def _parse_money(s: str) -> int | None:
    """'$28,216,944' → 28216944. '-' or 'n/a' → None."""
    s = s.strip()
    if not s or s in {"-", "n/a", "N/A", "--"}:
        return None
    m = MONEY_RE.search(s.replace(",", ""))
    if m:
        try:
            return int(float(m.group(1)))
        except ValueError:
            return None
    return None


def _parse_service_time(s: str) -> float | None:
    """'8.000' → 8.0. '-' / 'n/a' → None."""
    s = s.strip()
    if not s or s in {"-", "n/a", "N/A"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _clean_text(s: str) -> str:
    """Strip HTML tags + collapse whitespace."""
    s = TAG_RE.sub("", s)
    return " ".join(s.split())


def _extract_table(html: str, table_id: str) -> str | None:
    """Return inner HTML of a `<table id="X">` element."""
    m = re.search(
        rf'<table id="{table_id}"[^>]*>(.*?)</table>',
        html,
        re.DOTALL,
    )
    return m.group(1) if m else None


def parse_payroll_table(
    table_html: str, table_type: str, team_bref: str, season: int, slug: str
) -> list[dict[str, Any]]:
    """Parse a single payroll table (active / dead / injured) into rows."""
    rows_out: list[dict[str, Any]] = []
    rows = ROW_RE.findall(table_html)
    for row in rows:
        cells = CELL_RE.findall(row)
        if len(cells) < 5:
            continue  # header or partial row
        # First cell has the player link
        link_match = PLAYER_LINK_RE.search(row)
        if not link_match:
            continue
        spotrac_id = int(link_match.group(1))
        slug_seg = link_match.group(2)
        clean_cells = [_clean_text(c) for c in cells]
        # The player-name cell has a leading-uppercase-name span we want to skip.
        # The visible name is the last text node in the first <td>.
        name_match = re.search(r'<a href="[^"]+"[^>]*>([^<]+)</a>', cells[0])
        player_name = (
            name_match.group(1).strip()
            if name_match
            else clean_cells[0].split()[-2] + " " + clean_cells[0].split()[-1]
        )
        # Column mapping for active table:
        # 0=name 1=position 2=service 3=acquired 4=status 5=base 6=cap 7=bonus 8=incentives
        position = clean_cells[1] if len(clean_cells) > 1 else None
        service_time = _parse_service_time(clean_cells[2]) if len(clean_cells) > 2 else None
        acquired = clean_cells[3] if len(clean_cells) > 3 else None
        status = clean_cells[4] if len(clean_cells) > 4 else None
        base = _parse_money(clean_cells[5]) if len(clean_cells) > 5 else None
        cap = _parse_money(clean_cells[6]) if len(clean_cells) > 6 else None
        bonus = _parse_money(clean_cells[7]) if len(clean_cells) > 7 else None
        incentives = _parse_money(clean_cells[8]) if len(clean_cells) > 8 else None

        rows_out.append(
            {
                "spotrac_id": spotrac_id,
                "mlb_player_id": None,  # filled in by name-match pass
                "player_name": player_name,
                "team_bref": team_bref,
                "season": season,
                "position": position,
                "service_time": service_time,
                "acquired_method": acquired,
                "status": status,
                "base_salary": base,
                "cap_hit": cap,
                "signing_bonus": bonus,
                "incentives": incentives,
                "table_type": table_type,
                "spotrac_slug": slug_seg,
                "source": SOURCE,
            }
        )
    return rows_out


def fetch_team_payroll(
    client: httpx.Client, team_bref: str, season: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Fetch + parse one team's payroll page. Returns (contract rows, totals)."""
    slug = TEAM_SLUG_BY_BREF[team_bref]
    if season >= 2025:
        url = PAYROLL_URL_CURRENT.format(slug=slug)
    else:
        url = PAYROLL_URL_HISTORICAL.format(slug=slug, year=season)
    r = client.get(url, timeout=30.0, follow_redirects=True)
    r.raise_for_status()
    html = r.text

    all_rows: list[dict[str, Any]] = []
    for table_id, table_type in (
        ("table_active", "active"),
        ("table_dead", "dead"),
        ("table_injured", "injured"),
    ):
        table_html = _extract_table(html, table_id)
        if table_html:
            all_rows.extend(parse_payroll_table(table_html, table_type, team_bref, season, slug))

    # Team-level totals: sum cap_hit per table_type
    totals: dict[str, int] = {"active": 0, "dead": 0, "injured": 0}
    for row in all_rows:
        if row["cap_hit"] is not None:
            totals[row["table_type"]] += row["cap_hit"]
    return all_rows, totals


def _resolve_mlb_ids(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    """Populate mlb_player_id via exact name match against mlb_people."""
    if not rows:
        return
    name_set = {r["player_name"] for r in rows}
    name_list = ",".join("'" + n.replace("'", "''") + "'" for n in name_set)
    mapping = {
        n: pid
        for n, pid in conn.execute(
            f"SELECT full_name, mlb_player_id FROM mlb_people WHERE full_name IN ({name_list})"
        ).fetchall()
    }
    for r in rows:
        r["mlb_player_id"] = mapping.get(r["player_name"])


def _upsert(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_sp", df)
    try:
        cols = (
            "spotrac_id, mlb_player_id, player_name, team_bref, season, "
            "position, service_time, acquired_method, status, base_salary, "
            "cap_hit, signing_bonus, incentives, table_type, spotrac_slug, source"
        )
        conn.execute(
            f"INSERT INTO spotrac_player_contracts ({cols}) "
            f"SELECT {cols} FROM _staging_sp "
            "ON CONFLICT (spotrac_id, season, table_type) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_sp")


def _upsert_team_payroll(
    conn: duckdb.DuckDBPyConnection,
    team_bref: str,
    season: int,
    totals: dict[str, int],
    active_count: int,
) -> None:
    """Insert a team-payroll-summary row computed from the parsed contracts."""
    total = totals["active"] + totals["dead"] + totals["injured"]
    conn.execute(
        "INSERT INTO spotrac_team_payroll "
        "(team_bref, team_slug, season, active_players, active_payroll, "
        "dead_money, injured_payroll, total_payroll, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (team_bref, season) DO NOTHING",
        [
            team_bref,
            TEAM_SLUG_BY_BREF[team_bref],
            season,
            active_count,
            totals["active"],
            totals["dead"],
            totals["injured"],
            total,
            SOURCE,
        ],
    )


def ingest_year(year: int, team_filter: tuple[str, ...] | None = None) -> int:
    """Ingest payroll data for every (or a subset of) team for one season."""
    teams_iter = team_filter or tuple(TEAM_SLUG_BY_BREF.keys())
    total_rows = 0
    with httpx.Client(headers=BROWSER_HEADERS) as client, db.connect() as conn:
        schemas.initialize(conn)
        for team_bref in teams_iter:
            try:
                rows, totals = fetch_team_payroll(client, team_bref, year)
            except httpx.HTTPError as exc:
                logger.warning("spotrac %s %d failed: %s", team_bref, year, exc)
                continue
            _resolve_mlb_ids(conn, rows)
            _upsert(conn, rows)
            active_count = sum(1 for r in rows if r["table_type"] == "active")
            _upsert_team_payroll(conn, team_bref, year, totals, active_count)
            total_rows += len(rows)
            logger.info(
                "spotrac %s %d: %d players, active=$%s, dead=$%s, injured=$%s",
                team_bref,
                year,
                len(rows),
                f"{totals['active']:,}",
                f"{totals['dead']:,}",
                f"{totals['injured']:,}",
            )
            time.sleep(RATE_LIMIT_SECONDS)
    return total_rows


def ingest_range(start: int = 2010, end: int = 2025) -> int:
    """Ingest payroll data across a year range for all 30 teams."""
    total = 0
    for year in range(start, end + 1):
        total += ingest_year(year)
    return total
