"""Monthly pitcher pitch-arsenal aggregates from Baseball Savant.

Fetches per-(pitcher, pitch_type) monthly aggregates for velo, spin, and
release position. Used by the decline-drift detector to find within-season
and cross-season trends before surface stats (ERA, xFIP) react.

Endpoint: Baseball Savant pitch-arsenal leaderboard JSON with date filters.
  https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats?
      type=pitcher&pitchType=&year={year}&min=1
      &game_date_gt={YYYY-MM-DD}&game_date_lt={YYYY-MM-DD}

Response: JSON object with ``data`` key → list of per-pitcher-per-pitch-type rows.

Coverage: 2021+ only (modern Statcast era with stable pitch classification).
Active months: April (4) through October (10) inclusive.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import httpx

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

SOURCE = "baseball-savant"
RATE_LIMIT_SECONDS = 0.5

# Active MLB months per season (no Jan-Mar spring training in Statcast leaderboard)
_ACTIVE_MONTHS = (4, 5, 6, 7, 8, 9, 10)

_LEADERBOARD_URL = (
    "https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats"
    "?type=pitcher&pitchType=&year={year}&min=1&hand=&run_value=False"
    "&game_date_gt={date_gt}&game_date_lt={date_lt}"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; savage-trade-evaluator/0.1; research only) "
        "AppleWebKit/537.36 (KHTML, like Gecko)"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats",
}


def _month_range(year: int, month: int) -> tuple[str, str]:
    """Return (YYYY-MM-01, YYYY-MM-{last_day}) for the given month."""
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day:02d}"


def _fetch_month(
    client: httpx.Client,
    year: int,
    month: int,
) -> list[dict[str, Any]]:
    """Fetch pitch-arsenal leaderboard for one month.

    Returns list of row dicts with normalised column names.
    Raises httpx.HTTPError on network failure (caller logs and continues).
    """
    date_gt, date_lt = _month_range(year, month)
    url = _LEADERBOARD_URL.format(year=year, date_gt=date_gt, date_lt=date_lt)
    resp = client.get(url)
    resp.raise_for_status()

    payload = resp.json()
    raw_rows: list[dict[str, Any]] = (
        payload if isinstance(payload, list) else payload.get("data", [])
    )

    rows: list[dict[str, Any]] = []
    for r in raw_rows:
        pitcher_id = r.get("pitcher_id") or r.get("player_id")
        if not pitcher_id:
            continue
        pitch_type = str(r.get("pitch_type") or r.get("pitch_name") or "").strip()
        if not pitch_type:
            continue
        n = int(r.get("pitches") or r.get("n_pitches") or 0)
        if n < 5:
            continue

        rows.append(
            {
                "pitcher_id": int(pitcher_id),
                "pitcher_name": str(r.get("player_name") or r.get("pitcher_name") or ""),
                "pitch_type": pitch_type,
                "year_id": year,
                "month": month,
                "n_pitches": n,
                "mean_velo": _safe_float(r.get("release_speed") or r.get("avg_speed")),
                "mean_spin": _safe_float(r.get("release_spin_rate") or r.get("avg_spin")),
                "mean_release_x": _safe_float(r.get("release_pos_x") or r.get("avg_release_x")),
                "mean_release_z": _safe_float(r.get("release_pos_z") or r.get("avg_release_z")),
                "mean_pfx_x": _safe_float(r.get("pfx_x") or r.get("avg_pfx_x")),
                "mean_pfx_z": _safe_float(r.get("pfx_z") or r.get("avg_pfx_z")),
            }
        )

    return rows


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ingest(
    start_year: int = 2021,
    end_year: int | None = None,
    skip_existing: bool = True,
) -> int:
    """Fetch and store monthly pitch-arsenal trends for all active seasons.

    Args:
        start_year: First season to ingest (2021 minimum for stable classification).
        end_year: Last season inclusive. Defaults to current year.
        skip_existing: Skip (year, month) combos already in the table.

    Returns:
        Total rows inserted.
    """
    import datetime

    if end_year is None:
        end_year = datetime.date.today().year

    start_year = max(start_year, 2021)

    with db.connect(read_only=True) as conn:
        existing: set[tuple[int, int]] = {
            (int(r[0]), int(r[1]))
            for r in conn.execute(
                "SELECT DISTINCT year_id, month FROM pitcher_monthly_trends"
            ).fetchall()
        }

    total_inserted = 0
    n_failed = 0

    with httpx.Client(headers=_HEADERS, timeout=30.0, follow_redirects=True) as client:
        for year in range(start_year, end_year + 1):
            current_month = date.today().month if year == end_year else 10
            for month in _ACTIVE_MONTHS:
                if month > current_month and year == end_year:
                    break
                if skip_existing and (year, month) in existing:
                    logger.debug("skip existing: %d/%02d", year, month)
                    continue

                try:
                    rows = _fetch_month(client, year, month)
                except httpx.HTTPError as exc:
                    logger.warning("fetch failed %d/%02d: %s", year, month, exc)
                    n_failed += 1
                    continue
                except Exception as exc:
                    logger.warning("parse error %d/%02d: %s", year, month, exc)
                    n_failed += 1
                    continue

                if not rows:
                    logger.warning("no data returned for %d/%02d", year, month)
                    continue

                with db.connect() as conn:
                    # Delete then re-insert for this month
                    conn.execute(
                        "DELETE FROM pitcher_monthly_trends WHERE year_id = ? AND month = ?",
                        [year, month],
                    )
                    for r in rows:
                        conn.execute(
                            """
                            INSERT INTO pitcher_monthly_trends
                                (pitcher_id, pitcher_name, pitch_type, year_id, month,
                                 n_pitches, mean_velo, mean_spin,
                                 mean_release_x, mean_release_z,
                                 mean_pfx_x, mean_pfx_z, source)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [
                                r["pitcher_id"],
                                r["pitcher_name"],
                                r["pitch_type"],
                                r["year_id"],
                                r["month"],
                                r["n_pitches"],
                                r["mean_velo"],
                                r["mean_spin"],
                                r["mean_release_x"],
                                r["mean_release_z"],
                                r["mean_pfx_x"],
                                r["mean_pfx_z"],
                                SOURCE,
                            ],
                        )
                    total_inserted += len(rows)

                logger.info("inserted %d rows for %d/%02d", len(rows), year, month)
                time.sleep(RATE_LIMIT_SECONDS)

    if n_failed:
        logger.warning("SKIPPED: %d month fetches failed", n_failed)

    logger.info("statcast-monthly ingest complete: %d rows inserted", total_inserted)
    return total_inserted
