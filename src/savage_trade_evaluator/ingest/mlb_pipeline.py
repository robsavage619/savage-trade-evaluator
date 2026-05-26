"""Ingest MLB Pipeline current top-100 prospect rankings from mlb.com.

MLB Pipeline (mlb.com/prospects) publishes a current top-100 with 20-80 scouting
grades. Two public, un-gated sources (plain httpx — no Cloudflare, no Firecrawl):

  1. Rankings page ``/prospects/stats/top-prospects`` server-injects the list as a
     JS global ``data = [...]`` (rank, MLBAM playerId, team, age, position, MiLB
     stats). We regex that array out of the HTML.
  2. Per-player ``/prospects/stats/scouting-report?playerId={id}`` returns JSON
     whose ``prospect_json.prospectBio[].contentText`` embeds the tool grades as
     ``Scouting grades: Hit: 50 | Power: 55 | ... | Overall: 55``. The Overall is
     MLB Pipeline's FV-equivalent (20-80), comparable to FanGraphs FV / TJStats FV.

player_id is MLBAM — no bridging. This is a current snapshot (the page is
current-only); we key on (fetched_at, mlbam_id) so snapshots accumulate.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

SOURCE = "mlb-pipeline"
RANKINGS_URL = "https://www.mlb.com/prospects/stats/top-prospects"
SCOUTING_URL = "https://www.mlb.com/prospects/stats/scouting-report"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TIMEOUT = 30
RATE_LIMIT_SECONDS = 0.4

# "Scouting grades: Hit: 50 | Power: 55 | ... | Overall: 55"
_GRADES_RE = re.compile(r"Scouting grades:\s*(.+?)</p>", re.I | re.S)
_GRADE_PAIR_RE = re.compile(r"([A-Za-z][A-Za-z ]*?):\s*(\d{2})")
_DATA_GLOBAL_RE = re.compile(r"\bdata\s*=\s*(\[.*?\])\s*;", re.S)

# MLB Pipeline grade label -> our column name.
_GRADE_COLS = {
    "hit": "hit",
    "power": "power",
    "run": "run",
    "arm": "arm",
    "field": "field",
    "fastball": "fastball",
    "slider": "slider",
    "curveball": "curveball",
    "changeup": "changeup",
    "control": "control",
    "overall": "overall_grade",
}


def _normalize(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", ascii_only.lower()).strip()


def _coerce_int(val: Any) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def fetch_rankings(client: httpx.Client) -> list[dict[str, Any]]:
    """Pull the rankings page and extract the embedded ``data`` global."""
    resp = client.get(RANKINGS_URL, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    m = _DATA_GLOBAL_RE.search(resp.text)
    if not m:
        raise RuntimeError("could not locate embedded 'data' global on rankings page")
    return json.loads(m.group(1))


def fetch_scouting(client: httpx.Client, mlbam_id: int) -> dict[str, Any]:
    """Pull one player's scouting report; return parsed grades + eta/drafted/signed.

    Returns an empty dict if the report is missing or unparseable.
    """
    resp = client.get(
        SCOUTING_URL, params={"playerId": mlbam_id}, headers=HEADERS, timeout=TIMEOUT
    )
    resp.raise_for_status()
    try:
        payload = resp.json()
    except json.JSONDecodeError:
        return {}
    if not payload:
        return {}
    pj = payload[0].get("prospect_json", {})
    out: dict[str, Any] = {
        "eta": _coerce_int(pj.get("eta")),
        "drafted": (pj.get("drafted") or None),
        "signed": (pj.get("signed") or None),
    }
    player = pj.get("player", {})
    if isinstance(player, dict):
        out["bat_side"] = player.get("batSideCode") or None
        out["throw_side"] = player.get("pitchHandCode") or None

    # Grades live in the prospectBio prose: "Scouting grades: Hit: 50 | ...".
    bio = pj.get("prospectBio")
    text = ""
    if isinstance(bio, list):
        text = " ".join(b.get("contentText", "") for b in bio if isinstance(b, dict))
    gm = _GRADES_RE.search(text)
    if gm:
        for label, grade in _GRADE_PAIR_RE.findall(gm.group(1)):
            col = _GRADE_COLS.get(label.strip().lower())
            if col:
                out[col] = float(grade)
    return out


def ingest(fetched_at: datetime | None = None, with_grades: bool = True) -> int:
    """Fetch current top-100 + (optionally) per-player grades; upsert a snapshot.

    Args:
        fetched_at: Snapshot timestamp. Defaults to now (UTC).
        with_grades: If True, fetch each player's scouting report for tool grades.

    Returns:
        Number of rows inserted.
    """
    if fetched_at is None:
        fetched_at = datetime.now(UTC).replace(tzinfo=None)

    rows: list[dict[str, Any]] = []
    with httpx.Client(follow_redirects=True) as client:
        ranking = fetch_rankings(client)
        logger.info("fetched %d MLB Pipeline ranking rows", len(ranking))
        for rec in ranking:
            mlbam = _coerce_int(rec.get("playerId"))
            if mlbam is None:
                continue
            name = rec.get("name", "").strip()
            row: dict[str, Any] = {
                "fetched_at": fetched_at,
                "mlbam_id": mlbam,
                "rank": _coerce_int(rec.get("rank")),
                "player_name": name,
                "player_name_norm": _normalize(name),
                "team": (rec.get("team") or None),
                "parent_org_id": _coerce_int(rec.get("teamId")),
                "position": (rec.get("position") or None),
                "age": float(rec["age"]) if rec.get("age") not in (None, "") else None,
                "eta": None,
                "overall_grade": None,
                "hit": None, "power": None, "run": None, "arm": None, "field": None,
                "fastball": None, "slider": None, "curveball": None,
                "changeup": None, "control": None,
                "bat_side": None, "throw_side": None,
                "drafted": None, "signed": None,
            }
            if with_grades:
                try:
                    row.update(fetch_scouting(client, mlbam))
                except httpx.HTTPError as exc:
                    logger.warning("scouting fetch failed for %d: %s", mlbam, exc)
                time.sleep(RATE_LIMIT_SECONDS)
            rows.append(row)

    if not rows:
        logger.warning("no MLB Pipeline rows parsed")
        return 0

    df = pd.DataFrame(rows)
    cols = ", ".join(df.columns)
    with db.connect() as conn:
        conn.register("_staging_mlbpipe", df)
        try:
            conn.execute(
                f"INSERT INTO mlb_pipeline_prospects ({cols}) SELECT {cols} "
                f"FROM _staging_mlbpipe ON CONFLICT (fetched_at, mlbam_id) DO NOTHING"
            )
        finally:
            conn.unregister("_staging_mlbpipe")
    n = len(rows)
    logger.info("ingested %d MLB Pipeline prospect rows (snapshot %s)", n, fetched_at.date())
    return n
