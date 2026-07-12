"""MLBTR (MLB Trade Rumors) post archive ingest.

Fetches all post URLs + dates via WordPress XML sitemaps (52 files, ~1000 posts
each). Post type is classified from slug keywords; team names are extracted via
a nickname-to-bref lookup. No individual post HTML scraping needed for v1.

URL structure: /{year}/{month}/{slug}.html
Date is extracted from the URL path. Lastmod datetime from sitemap is stored as
ingested_at, not used as the canonical post_date (URL path date is canonical).

Weak-labeling for acceptance model:
  - trade_rumor posts where the involved players later appear in a trade
    transaction → positive (consummated)
  - trade_rumor posts where no matching transaction is found within 90 days →
    weak negative (rumored but rejected)
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import httpx

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

SOURCE = "mlbtraderumors"
SITEMAP_BASE = "https://www.mlbtraderumors.com/wp-sitemap-posts-post-{n}.xml"
N_SITEMAPS = 52
RATE_LIMIT_SECONDS = 0.25  # polite; sitemaps are XML, lightweight

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; savage-trade-evaluator/0.1; research only) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    ),
    "Accept": "application/xml,text/xml,*/*;q=0.8",
}

# --- post-type keyword classification ---
# Order matters: first match wins
_TYPE_RULES: list[tuple[str, list[str]]] = [
    (
        "minor_move",
        [
            "minor-moves",
            "dfa",
            "outright",
            "option",
            "recalled",
            "selected-",
            "claimed",
            "rule-5",
            "released",
        ],
    ),
    (
        "links_roundup",
        [
            "-links",
            "-notes",
            "roundup",
            "transactions-",
        ],
    ),
    (
        "injury",
        [
            "-injury",
            "-injured",
            "il-stint",
            "tommy-john",
            "surgery",
            "fracture",
        ],
    ),
    (
        "extension",
        [
            "-extension",
            "extends-",
            "extended-",
        ],
    ),
    (
        "signing",
        [
            "-signed-",
            "-sign-",
            "signing",
            "-agreement",
            "-agrees-",
            "-deal-",
            "-contract-",
            "free-agent-",
        ],
    ),
    (
        "trade_rumor",
        [
            "-trade-",
            "trade-rumor",
            "exploring-trade",
            "discussing",
            "discussed",
            "listening-to",
            "interested-in",
            "targeting",
            "-rumors",
            "-rumor",
            "sources-say",
            "-deal-",
            "-talks-",
            "in-play",
            "-pursuit",
        ],
    ),
]


def _classify_slug(slug: str) -> str:
    s = slug.lower()
    for post_type, keywords in _TYPE_RULES:
        if any(kw in s for kw in keywords):
            return post_type
    return "other"


# --- team nickname → bref code ---
_NICKNAME_TO_BREF: dict[str, str] = {
    "angels": "LAA",
    "astros": "HOU",
    "athletics": "OAK",
    "blue-jays": "TOR",
    "bluejays": "TOR",
    "braves": "ATL",
    "brewers": "MIL",
    "cardinals": "STL",
    "cubs": "CHC",
    "diamondbacks": "ARI",
    "dbacks": "ARI",
    "dodgers": "LAD",
    "giants": "SFG",
    "guardians": "CLE",
    "indians": "CLE",
    "mariners": "SEA",
    "marlins": "MIA",
    "mets": "NYM",
    "nationals": "WSN",
    "orioles": "BAL",
    "padres": "SDP",
    "phillies": "PHI",
    "pirates": "PIT",
    "rangers": "TEX",
    "rays": "TBR",
    "red-sox": "BOS",
    "redsox": "BOS",
    "reds": "CIN",
    "rockies": "COL",
    "royals": "KCR",
    "tigers": "DET",
    "twins": "MIN",
    "white-sox": "CHW",
    "whitesox": "CHW",
    "yankees": "NYY",
}


def _extract_teams(slug: str) -> list[str]:
    s = slug.lower()
    found: list[str] = []
    seen: set[str] = set()
    for nick, bref in _NICKNAME_TO_BREF.items():
        if nick in s and bref not in seen:
            found.append(bref)
            seen.add(bref)
    return found


_SLUG_STOP_WORDS: frozenset[str] = frozenset(
    {
        "the", "and", "or", "of", "in", "on", "to", "a", "an", "for",
        "with", "from", "by", "at", "as", "is", "are", "not", "no",
        "would", "could", "should", "have", "has", "will", "may", "might",
        "report", "reports", "sources", "notes", "links", "moves", "move",
        "minor", "major", "trade", "trades", "traded", "rumor", "rumors",
        "deal", "deals", "sign", "signs", "signed", "signing", "extension",
        "latest", "update", "updates", "news", "following", "considering",
        "discussing", "discussed", "exploring", "listening",
    }
)


def _extract_players(slug: str) -> list[str]:
    """Return slug tokens that could be player name parts (length >= 3, not stop words)."""
    tokens = [t.strip("-") for t in slug.lower().split("-") if t.strip("-")]
    return [t for t in tokens if len(t) >= 3 and t not in _SLUG_STOP_WORDS]


def _parse_date_from_url(url: str) -> date | None:
    """Extract post date from URL path like /{year}/{month}/{slug}.html."""
    m = re.search(r"/(\d{4})/(\d{2})/", url)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), 1)
    except ValueError:
        return None


def _parse_sitemap(xml_text: str) -> list[dict[str, Any]]:
    """Parse a WordPress urlset XML into list of {url, post_date, slug, ...} dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("sitemap parse error: %s", exc)
        return []

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    rows: list[dict[str, Any]] = []

    for url_el in root.findall("sm:url", ns):
        loc_el = url_el.find("sm:loc", ns)
        if loc_el is None or not loc_el.text:
            continue
        url = loc_el.text.strip()

        # Extract slug from URL (last path component, strip .html)
        slug_raw = url.rstrip("/").rsplit("/", 1)[-1]
        slug = slug_raw.replace(".html", "").replace(".htm", "")

        post_date = _parse_date_from_url(url)
        if post_date is None:
            continue

        post_type = _classify_slug(slug)
        teams = _extract_teams(slug)
        players = _extract_players(slug)

        rows.append(
            {
                "url": url,
                "post_date": post_date,
                "slug": slug,
                "post_type": post_type,
                "teams_mentioned": json.dumps(teams),
                "players_mentioned": json.dumps(players),
                "is_trade_rumor": post_type == "trade_rumor",
            }
        )

    return rows


def ingest(
    start_sitemap: int = 1,
    end_sitemap: int = N_SITEMAPS,
    upsert: bool = True,
) -> int:
    """Scrape MLBTR WordPress sitemaps and load into ``trade_rumors``.

    Args:
        start_sitemap: First sitemap index (1-based). Default 1.
        end_sitemap: Last sitemap index inclusive. Default 52.
        upsert: If True, skip URLs already in table. If False, delete+reload.

    Returns:
        Number of rows inserted.
    """
    rows_total: list[dict[str, Any]] = []
    n_failed = 0

    with httpx.Client(headers=HEADERS, timeout=30.0) as client:
        for n in range(start_sitemap, end_sitemap + 1):
            url = SITEMAP_BASE.format(n=n)
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("sitemap %d fetch failed: %s", n, exc)
                n_failed += 1
                continue

            rows = _parse_sitemap(resp.text)
            rows_total.extend(rows)
            logger.info("sitemap %d/%d: %d posts parsed", n, end_sitemap, len(rows))
            time.sleep(RATE_LIMIT_SECONDS)

    if n_failed:
        logger.warning(
            "SKIPPED: %d sitemaps failed (out of %d)", n_failed, end_sitemap - start_sitemap + 1
        )

    if not rows_total:
        logger.warning("no rows parsed — nothing to load")
        return 0

    inserted = 0
    with db.connect() as conn:
        if not upsert:
            conn.execute("DELETE FROM trade_rumors WHERE source = 'mlbtraderumors'")

        for r in rows_total:
            if upsert:
                exists = conn.execute(
                    "SELECT 1 FROM trade_rumors WHERE url = ?", [r["url"]]
                ).fetchone()
                if exists:
                    continue
            conn.execute(
                """
                INSERT INTO trade_rumors
                    (url, post_date, slug, post_type, teams_mentioned,
                     players_mentioned, is_trade_rumor, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    r["url"],
                    r["post_date"],
                    r["slug"],
                    r["post_type"],
                    r["teams_mentioned"],
                    r["players_mentioned"],
                    r["is_trade_rumor"],
                    SOURCE,
                ],
            )
            inserted += 1

    logger.info(
        "mlbtr ingest complete: %d rows inserted from %d parsed",
        inserted,
        len(rows_total),
    )
    return inserted
