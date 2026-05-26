"""Ingest TJStats prospect data from the public WordPress JSON API.

TJStats (tjstats.ca, Thomas Nestico) publishes live prospect rankings,
per-pitch scouting grades for pitchers, and tool grades for batters via a
public WP JSON API. player_id is an MLBAM ID — no bridging needed.

Endpoints:
  /wp-json/tjstats/v1/rankings        → tjstats_prospect_rankings
  /wp-json/tjstats/v1/scout-pitchers  → tjstats_scout_pitchers
  /wp-json/tjstats/v1/scout-batters   → tjstats_scout_batters

These are point-in-time snapshots. We record fetched_at as the primary key
partition so multiple snapshots can coexist (useful for tracking drift).
Use the most-recent snapshot for forward scoring.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

import httpx
import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

BASE_URL = "https://tjstats.ca/wp-json/tjstats/v1"
TIMEOUT = 30


def _get(path: str) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/{path}"
    resp = httpx.get(url, timeout=TIMEOUT, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()


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


def _coerce_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def ingest_rankings(fetched_at: datetime | None = None) -> int:
    """Fetch /rankings and insert into tjstats_prospect_rankings.

    Args:
        fetched_at: Snapshot timestamp. Defaults to now (UTC).

    Returns:
        Number of rows inserted.
    """
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)

    raw = _get("rankings")
    rows = []
    for r in raw:
        rows.append({
            "fetched_at": fetched_at,
            "player_id": str(r["player_id"]),
            "rank_value": _coerce_int(r.get("rank_value")),
            "prev_rank": _coerce_int(r.get("prev_rank")),
            "player_name": r.get("name", "").strip(),
            "player_name_norm": _normalize(r.get("name", "")),
            "position": r.get("position", "").strip() or None,
            "parent_org_id": str(r["parent_org_id"]) if r.get("parent_org_id") else None,
            "fv": _coerce_float(r.get("fv")),
            "age": _coerce_float(r.get("age")),
            "height": r.get("height", "").strip() or None,
            "weight": _coerce_float(r.get("weight")),
            "bat_side": r.get("bat_side", "").strip() or None,
            "throw_side": r.get("throw_side", "").strip() or None,
            "report": (r.get("report") or "").strip() or None,
        })

    if not rows:
        logger.warning("rankings endpoint returned 0 rows")
        return 0

    df = pd.DataFrame(rows)
    with db.connect() as conn:
        conn.register("_staging_rankings", df)
        try:
            conn.execute("""
                INSERT INTO tjstats_prospect_rankings
                    (fetched_at, player_id, rank_value, prev_rank, player_name,
                     player_name_norm, position, parent_org_id, fv, age, height,
                     weight, bat_side, throw_side, report)
                SELECT
                    fetched_at, player_id, rank_value, prev_rank, player_name,
                    player_name_norm, position, parent_org_id, fv, age, height,
                    weight, bat_side, throw_side, report
                FROM _staging_rankings
                ON CONFLICT (fetched_at, player_id) DO NOTHING
            """)
        finally:
            conn.unregister("_staging_rankings")
        n = len(rows)

    logger.info("ingested %d tjstats ranking rows (snapshot %s)", n, fetched_at.date())
    return n


def ingest_scout_pitchers(fetched_at: datetime | None = None) -> int:
    """Fetch /scout-pitchers and insert into tjstats_scout_pitchers."""
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)

    raw = _get("scout-pitchers")
    rows = []
    for r in raw:
        rows.append({
            "fetched_at": fetched_at,
            "player_id": str(r["player_id"]),
            "player_name": (r.get("fullName") or r.get("player", "")).strip() or None,
            "rank_value": _coerce_int(r.get("rank_value")),
            "fv": _coerce_float(r.get("fv")),
            "fastball_pv": _coerce_float(r.get("fastball_pv")),
            "fastball_fv": _coerce_float(r.get("fastball_fv")),
            "cutter_pv": _coerce_float(r.get("cutter_pv")),
            "cutter_fv": _coerce_float(r.get("cutter_fv")),
            "slider_pv": _coerce_float(r.get("slider_pv")),
            "slider_fv": _coerce_float(r.get("slider_fv")),
            "curveball_pv": _coerce_float(r.get("curveball_pv")),
            "curveball_fv": _coerce_float(r.get("curveball_fv")),
            "changeup_pv": _coerce_float(r.get("changeup_pv")),
            "changeup_fv": _coerce_float(r.get("changeup_fv")),
            "splitter_pv": _coerce_float(r.get("splitter_pv")),
            "splitter_fv": _coerce_float(r.get("splitter_fv")),
            "command_pv": _coerce_float(r.get("command_pv")),
            "command_fv": _coerce_float(r.get("command_fv")),
            "eta": _coerce_int(r.get("eta")),
            "risk": (r.get("risk") or "").strip() or None,
            "report": (r.get("report") or "").strip() or None,
            "report_date": r.get("report_date") or None,
        })

    if not rows:
        logger.warning("scout-pitchers endpoint returned 0 rows")
        return 0

    df = pd.DataFrame(rows)
    with db.connect() as conn:
        conn.register("_staging_sp", df)
        try:
            conn.execute("""
                INSERT INTO tjstats_scout_pitchers
                    (fetched_at, player_id, player_name, rank_value, fv,
                     fastball_pv, fastball_fv, cutter_pv, cutter_fv,
                     slider_pv, slider_fv, curveball_pv, curveball_fv,
                     changeup_pv, changeup_fv, splitter_pv, splitter_fv,
                     command_pv, command_fv, eta, risk, report, report_date)
                SELECT
                    fetched_at, player_id, player_name, rank_value, fv,
                    fastball_pv, fastball_fv, cutter_pv, cutter_fv,
                    slider_pv, slider_fv, curveball_pv, curveball_fv,
                    changeup_pv, changeup_fv, splitter_pv, splitter_fv,
                    command_pv, command_fv, eta, risk, report, report_date
                FROM _staging_sp
                ON CONFLICT (fetched_at, player_id) DO NOTHING
            """)
        finally:
            conn.unregister("_staging_sp")
        n = len(rows)

    logger.info("ingested %d tjstats pitcher scouting rows (snapshot %s)", n, fetched_at.date())
    return n


def ingest_scout_batters(fetched_at: datetime | None = None) -> int:
    """Fetch /scout-batters and insert into tjstats_scout_batters."""
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)

    raw = _get("scout-batters")
    rows = []
    for r in raw:
        rows.append({
            "fetched_at": fetched_at,
            "player_id": str(r["player_id"]),
            "player_name": (r.get("fullName") or r.get("player", "")).strip() or None,
            "rank_value": _coerce_int(r.get("rank_value")),
            "fv": _coerce_float(r.get("fv")),
            "hit_pv": _coerce_float(r.get("hit_pv")),
            "hit_fv": _coerce_float(r.get("hit_fv")),
            "power_pv": _coerce_float(r.get("power_pv")),
            "power_fv": _coerce_float(r.get("power_fv")),
            "decisions_pv": _coerce_float(r.get("decisions_pv")),
            "decisions_fv": _coerce_float(r.get("decisions_fv")),
            "speed_pv": _coerce_float(r.get("speed_pv")),
            "speed_fv": _coerce_float(r.get("speed_fv")),
            "defense_pv": _coerce_float(r.get("defense_pv")),
            "defense_fv": _coerce_float(r.get("defense_fv")),
            "eta": _coerce_int(r.get("eta")),
            "risk": (r.get("risk") or "").strip() or None,
            "report": (r.get("report") or "").strip() or None,
            "report_date": r.get("report_date") or None,
        })

    if not rows:
        logger.warning("scout-batters endpoint returned 0 rows")
        return 0

    df = pd.DataFrame(rows)
    with db.connect() as conn:
        conn.register("_staging_sb", df)
        try:
            conn.execute("""
                INSERT INTO tjstats_scout_batters
                    (fetched_at, player_id, player_name, rank_value, fv,
                     hit_pv, hit_fv, power_pv, power_fv,
                     decisions_pv, decisions_fv, speed_pv, speed_fv,
                     defense_pv, defense_fv, eta, risk, report, report_date)
                SELECT
                    fetched_at, player_id, player_name, rank_value, fv,
                    hit_pv, hit_fv, power_pv, power_fv,
                    decisions_pv, decisions_fv, speed_pv, speed_fv,
                    defense_pv, defense_fv, eta, risk, report, report_date
                FROM _staging_sb
                ON CONFLICT (fetched_at, player_id) DO NOTHING
            """)
        finally:
            conn.unregister("_staging_sb")
        n = len(rows)

    logger.info("ingested %d tjstats batter scouting rows (snapshot %s)", n, fetched_at.date())
    return n


def ingest_all(fetched_at: datetime | None = None) -> dict[str, int]:
    """Fetch and ingest all three TJStats endpoints in a single snapshot.

    Args:
        fetched_at: Shared snapshot timestamp. Defaults to now (UTC).

    Returns:
        Dict of {endpoint_name: rows_inserted}.
    """
    if fetched_at is None:
        fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "rankings": ingest_rankings(fetched_at),
        "scout_pitchers": ingest_scout_pitchers(fetched_at),
        "scout_batters": ingest_scout_batters(fetched_at),
    }
