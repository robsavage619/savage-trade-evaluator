"""Ingest current contracts, options and service time from Baseball Reference.

Each ``https://www.baseball-reference.com/teams/<CODE>/<club>-salaries-and-contracts.shtml``
page lists a club's players with a contract summary, exact service time and a
per-season cell: guaranteed dollars, a buyout plus option (the option type and
value sit in a tooltip, and ``[FA-*]`` says what happens if it is declined),
an arbitration projection, or FA.

Spotrac's contract-terms parse treats the free-agent year as the end of a
guaranteed deal, so a player-option or mutual-option year reads as guaranteed.
This source carries the option type, which is what that parse loses.

Pages are current-state snapshots. Rows are stored per ``as_of`` date so a
history of contract state builds up from the first ingest onward; nothing here
is retroactive. The two tables are created by this module rather than in
``storage/schemas.py`` while that file carries unrelated uncommitted changes.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import html as html_lib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

import httpx
import pandas as pd

from savage_trade_evaluator.config import DATA_DIR
from savage_trade_evaluator.ingest.front_office import (
    HEADERS,
    HTTP_TIMEOUT_SECONDS,
    RATE_LIMIT_SECONDS,
)
from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

SOURCE = "bref-contracts"
URL = "https://www.baseball-reference.com/teams/{code}/{slug}-salaries-and-contracts.shtml"
CACHE_DIR = DATA_DIR / "bref_contracts_cache"

# Baseball Reference's contracts pages live under older franchise codes for three
# clubs; the Athletics keep OAK even though the team page is ATH.
URL_CODE = {"LAA": "ANA", "MIA": "FLA", "TBR": "TBD"}

DDL = (
    """
    CREATE TABLE IF NOT EXISTS bref_contract_players (
        team_bref VARCHAR NOT NULL,
        as_of DATE NOT NULL,
        bref_id VARCHAR NOT NULL,
        mlb_player_id INTEGER,
        player_name VARCHAR NOT NULL,
        age INTEGER,
        mlb_experience VARCHAR,
        how_acquired VARCHAR,
        service_time DOUBLE,
        contract_summary VARCHAR,
        summary_years INTEGER,
        summary_total BIGINT,
        summary_first_season INTEGER,
        summary_last_season INTEGER,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_bref, as_of, bref_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bref_contract_years (
        team_bref VARCHAR NOT NULL,
        as_of DATE NOT NULL,
        bref_id VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        kind VARCHAR NOT NULL,
        amount BIGINT,
        option_type VARCHAR,
        option_value BIGINT,
        status_if_declined VARCHAR,
        raw_text VARCHAR,
        PRIMARY KEY (team_bref, as_of, bref_id, season)
    )
    """,
)

_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.DOTALL)
_CELL_RE = re.compile(r"<(?:td|th)([^>]*)>(.*?)</(?:td|th)>", re.DOTALL)
_STAT_RE = re.compile(r'data-stat="([a-z0-9_]+)"')
_BREF_ID_RE = re.compile(r'data-append-csv="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_ATTR_RE = re.compile(r'="[^"]*"')
_MONEY_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)\s*([MmKk]?)")
_OPTION_TIP_RE = re.compile(r'data-tip="\$([\d,.]+)\s*([MmKk]?)\s+([A-Za-z/ ]*?)\s*Option[^"]*"')
_DECLINED_RE = re.compile(r"\[(.+?)-\*\]")
_SUMMARY_RE = re.compile(r"(\d+)\s*yrs?\s*/\s*\$([\d,.]+)\s*([MmKk]?)\s*\((\d{2})-(\d{2})\)")
_PAYROLL_RE = re.compile(r'<table[^>]*id="payroll".*?</table>', re.DOTALL)


@dataclass(frozen=True)
class ContractYear:
    """One season of a player's contract status.

    Attributes:
        season: Calendar season of the cell.
        kind: ``guaranteed``, ``option``, ``arb``, ``pre_arb``, ``fa`` or ``other``.
        amount: Guaranteed dollars, the buyout for an option year, or the
            arbitration estimate; None when the cell gives no figure.
        option_type: ``team``, ``player``, ``mutual``, ``vesting`` or ``other``.
        option_value: Salary if the option is exercised.
        status_if_declined: ``FA`` or ``Arb-N`` when the option is declined.
        raw_text: The cell's visible text, kept so unrecognized shapes are visible.
    """

    season: int
    kind: str
    amount: int | None = None
    option_type: str | None = None
    option_value: int | None = None
    status_if_declined: str | None = None
    raw_text: str = ""


@dataclass(frozen=True)
class PlayerContract:
    """One player row from a club's contracts page."""

    bref_id: str
    name: str
    age: int | None
    mlb_experience: str | None
    how_acquired: str | None
    service_time: float | None
    summary: str | None
    summary_years: int | None
    summary_total: int | None
    summary_first_season: int | None
    summary_last_season: int | None
    years: list[ContractYear] = field(default_factory=list)


def _money(value: str, scale: str) -> int:
    return round(float(value.replace(",", "")) * {"m": 1_000_000, "k": 1_000}.get(scale.lower(), 1))


def _text(inner: str) -> str:
    # Tooltip attributes can contain markup of their own, which would end a tag early.
    inner = _ATTR_RE.sub('=""', inner)
    return re.sub(
        r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", inner)).replace("\xa0", " ")
    ).strip()


def parse_year_cell(season: int, inner: str) -> ContractYear | None:
    """Classify one per-season cell, or None for an empty cell.

    Args:
        season: Season the cell's column stands for.
        inner: The cell's inner HTML (the option type lives in a tooltip attribute).

    Returns:
        A :class:`ContractYear`. Shapes that match nothing come back as kind
        ``other`` with the raw text, never dropped.
    """
    text = _text(inner)
    if not text:
        return None
    money = _MONEY_RE.search(text)
    amount = _money(*money.groups()) if money else None
    declined = _DECLINED_RE.search(text)
    option = _OPTION_TIP_RE.search(inner)
    if option:
        raw_type = option.group(3).strip().lower()
        known = {"team", "player", "mutual", "vesting"}
        return ContractYear(
            season,
            "option",
            amount=amount,
            option_type=raw_type if raw_type in known else "other",
            option_value=_money(option.group(1), option.group(2)),
            status_if_declined=declined.group(1) if declined else None,
            raw_text=text,
        )
    if text.startswith("FA"):
        return ContractYear(season, "fa", raw_text=text)
    if text.startswith("Pre-Arb"):
        return ContractYear(season, "pre_arb", amount=amount, raw_text=text)
    if text.startswith("Arb"):
        return ContractYear(season, "arb", amount=amount, raw_text=text)
    if text.startswith("$") and money:
        return ContractYear(season, "guaranteed", amount=amount, raw_text=text)
    return ContractYear(season, "other", amount=amount, raw_text=text)


def parse_contracts_page(page: str) -> list[PlayerContract]:
    """Parse a club's salaries-and-contracts page into one record per player.

    Args:
        page: Page HTML.

    Returns:
        Player records in page order. Repeated header rows are skipped.

    Raises:
        ValueError: If the payroll table or its season header is missing, so a
            template change fails loudly instead of returning nothing.
    """
    table = _PAYROLL_RE.search(page)
    if table is None:
        raise ValueError("payroll table not found")
    rows = _ROW_RE.findall(table.group(0))
    seasons: dict[str, int] = {}
    for attrs, inner in _CELL_RE.findall(rows[0]):
        stat = _STAT_RE.search(attrs)
        label = _text(inner)
        if stat and stat.group(1).startswith("contract_y") and label.isdigit():
            seasons[stat.group(1)] = int(label)
    if not seasons:
        raise ValueError("season header not found")

    out: list[PlayerContract] = []
    for row in rows[1:]:
        cells = {}
        for attrs, inner in _CELL_RE.findall(row):
            stat = _STAT_RE.search(attrs)
            if stat:
                cells[stat.group(1)] = (attrs, inner)
        if "player" not in cells:
            continue
        bref_id = _BREF_ID_RE.search(cells["player"][0])
        if bref_id is None:
            continue

        def get(key: str, cells: dict = cells) -> str:
            return _text(cells[key][1]) if key in cells else ""

        summary = get("contract_summary")
        parsed = _SUMMARY_RE.search(summary)
        age, service = get("age"), get("service_time")
        out.append(
            PlayerContract(
                bref_id=bref_id.group(1),
                name=get("player"),
                age=int(age) if age.isdigit() else None,
                mlb_experience=get("experience") or None,
                how_acquired=get("how_acquired") or None,
                service_time=float(service) if re.fullmatch(r"\d+(\.\d+)?", service) else None,
                summary=summary or None,
                summary_years=int(parsed.group(1)) if parsed else None,
                summary_total=_money(parsed.group(2), parsed.group(3)) if parsed else None,
                summary_first_season=2000 + int(parsed.group(4)) if parsed else None,
                summary_last_season=2000 + int(parsed.group(5)) if parsed else None,
                years=[
                    y
                    for key, season in seasons.items()
                    if key in cells and (y := parse_year_cell(season, cells[key][1])) is not None
                ],
            )
        )
    return out


def fetch_team_page(bref_code: str, slug: str, client: httpx.Client, as_of: date) -> str:
    """Fetch one club's page, reading and writing the on-disk cache for ``as_of``."""
    path = CACHE_DIR / as_of.isoformat() / f"{bref_code}.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    resp = client.get(URL.format(code=URL_CODE.get(bref_code, bref_code), slug=slug))
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(resp.text, encoding="utf-8")
    return resp.text


def _slug(team_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", team_name.lower()).strip("-")


def ingest_all(as_of: date | None = None) -> int:
    """Fetch, parse and store all 30 clubs' contract pages for one snapshot date.

    Args:
        as_of: Snapshot date; defaults to today. Re-running a date replaces it.

    Returns:
        Player rows stored. Clubs that fail to fetch or parse are logged and
        counted in the warning, never silently skipped.
    """
    as_of = as_of or date.today()
    with db.connect(read_only=True) as conn:
        clubs = conn.execute(
            "SELECT bref_code, name FROM teams WHERE bref_code IS NOT NULL ORDER BY bref_code"
        ).fetchall()
        ids = dict(conn.execute("SELECT bref_id, mlb_player_id FROM chadwick_register").fetchall())
    total, failed, unrecognized = 0, [], 0
    with httpx.Client(
        timeout=HTTP_TIMEOUT_SECONDS, headers=HEADERS, follow_redirects=True
    ) as client:
        for code, name in clubs:
            cached = (CACHE_DIR / as_of.isoformat() / f"{code}.html").exists()
            try:
                players = parse_contracts_page(fetch_team_page(code, _slug(name), client, as_of))
            except (httpx.HTTPError, ValueError) as exc:
                logger.error("failed %s: %s", code, exc)
                failed.append(code)
                continue
            unrecognized += sum(y.kind == "other" for p in players for y in p.years)
            total += _store(code, as_of, players, ids)
            if not cached:
                time.sleep(RATE_LIMIT_SECONDS)
    if failed:
        logger.warning("clubs that failed: %s", ", ".join(failed))
    if unrecognized:
        logger.warning("%d contract cells had an unrecognized shape (kind='other')", unrecognized)
    return total


def _store(code: str, as_of: date, players: list[PlayerContract], ids: dict[str, int]) -> int:
    player_rows = [
        {
            "team_bref": code,
            "as_of": as_of,
            "bref_id": p.bref_id,
            "mlb_player_id": ids.get(p.bref_id),
            "player_name": p.name,
            "age": p.age,
            "mlb_experience": p.mlb_experience,
            "how_acquired": p.how_acquired,
            "service_time": p.service_time,
            "contract_summary": p.summary,
            "summary_years": p.summary_years,
            "summary_total": p.summary_total,
            "summary_first_season": p.summary_first_season,
            "summary_last_season": p.summary_last_season,
            "source": SOURCE,
        }
        for p in players
    ]
    year_rows = [
        {
            "team_bref": code,
            "as_of": as_of,
            "bref_id": p.bref_id,
            "season": y.season,
            "kind": y.kind,
            "amount": y.amount,
            "option_type": y.option_type,
            "option_value": y.option_value,
            "status_if_declined": y.status_if_declined,
            "raw_text": y.raw_text,
        }
        for p in players
        for y in p.years
    ]
    with db.connect() as conn:
        for ddl in DDL:
            conn.execute(ddl)
        conn.execute(
            "DELETE FROM bref_contract_players WHERE team_bref = ? AND as_of = ?", [code, as_of]
        )
        conn.execute(
            "DELETE FROM bref_contract_years WHERE team_bref = ? AND as_of = ?", [code, as_of]
        )
        for table, rows in (
            ("bref_contract_players", player_rows),
            ("bref_contract_years", year_rows),
        ):
            if not rows:
                continue
            frame = pd.DataFrame(rows)
            conn.register("_staging_bref", frame)
            try:
                cols = ", ".join(frame.columns)
                conn.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _staging_bref")
            finally:
                conn.unregister("_staging_bref")
    return len(player_rows)


def guaranteed_through(years: list[ContractYear]) -> int | None:
    """Last season of the unbroken run of guaranteed years from the first season shown.

    Args:
        years: A player's per-season cells, in season order.

    Returns:
        The last guaranteed season, or None when the first season is not guaranteed.
    """
    last = None
    for y in sorted(years, key=lambda y: y.season):
        if y.kind != "guaranteed" or (last is not None and y.season != last + 1):
            break
        last = y.season
    return last


def spotrac_conflicts(conn: duckdb.DuckDBPyConnection, as_of: date | None = None) -> pd.DataFrame:
    """Players whose Spotrac guaranteed window disagrees with Baseball Reference.

    Spotrac treats the season before its free-agent year as guaranteed. A player
    is flagged when Baseball Reference shows an option (or nothing at all) inside
    that window.

    Args:
        conn: Open DuckDB connection.
        as_of: Snapshot to compare against; defaults to the latest ingested.

    Returns:
        One row per flagged player with ``issue`` set to ``option_inside_window``,
        ``absent_from_bref`` (no club page lists him although Spotrac's window runs
        past the snapshot), ``expired`` (absent, and the window has ended), or
        ``spotrac_missing_fa_year`` (no window to compare).
    """
    latest = conn.execute("SELECT MAX(as_of) FROM bref_contract_players").fetchone()
    snap = as_of or (latest[0] if latest else None)
    if snap is None:
        raise ValueError("no Baseball Reference contract snapshot has been ingested")
    terms = conn.execute(
        "SELECT t.mlb_player_id, p.full_name, t.contract_years, t.contract_total, "
        "t.aav, t.free_agent_year "
        "FROM spotrac_contract_terms t LEFT JOIN mlb_people p USING (mlb_player_id) "
        "WHERE t.season = (SELECT MAX(season) FROM spotrac_contract_terms)"
    ).df()
    cells = conn.execute(
        "SELECT p.mlb_player_id, y.season, y.kind, y.option_type, y.option_value, y.amount "
        "FROM bref_contract_players p JOIN bref_contract_years y "
        "USING (team_bref, as_of, bref_id) WHERE p.as_of = ? AND p.mlb_player_id IS NOT NULL",
        [snap],
    ).df()
    rows = []
    # A deal whose window ended before the next season has simply run out.
    expired_before = snap.year + (1 if snap.month >= 11 else 0)
    by_player = {pid: g for pid, g in cells.groupby("mlb_player_id")}
    for t in terms.itertuples(index=False):
        g = by_player.get(t.mlb_player_id)
        missing_end = pd.isna(t.free_agent_year)
        spotrac_end = None if missing_end else int(t.free_agent_year) - 1
        base = {
            "mlb_player_id": t.mlb_player_id,
            "player": t.full_name,
            "spotrac_years": t.contract_years,
            "spotrac_total": t.contract_total,
            "spotrac_guaranteed_through": spotrac_end,
        }
        if missing_end:
            rows.append({**base, "issue": "spotrac_missing_fa_year"})
            continue
        spotrac_end = int(t.free_agent_year) - 1
        if g is None:
            rows.append(
                {**base, "issue": "expired" if spotrac_end < expired_before else "absent_from_bref"}
            )
            continue
        years = [
            ContractYear(int(r.season), r.kind, option_type=r.option_type)
            for r in g.itertuples(index=False)
        ]
        through = guaranteed_through(years)
        options = [y for y in years if y.kind == "option" and y.season <= spotrac_end]
        if options:
            first = min(options, key=lambda y: y.season)
            rows.append(
                {
                    **base,
                    "issue": "option_inside_window",
                    "bref_guaranteed_through": through,
                    "first_option_season": first.season,
                    "option_type": first.option_type,
                }
            )
    return pd.DataFrame(rows)
