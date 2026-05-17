"""Extended Statcast ingest: batter percentile ranks, pitcher arsenal, OAA.

Three Savant data sources we hadn't ingested before:
- ``statcast_batter_percentile_ranks``: hitter-side percentile-rank percentiles
  (xwoba, hard_hit%, chase%, sprint_speed, oaa, bat_speed). Hitter analog to
  the existing pitcher percentile_ranks table.
- ``statcast_pitcher_arsenal_stats``: per-(player, pitch_type) breakdown of
  whiff%, k%, run_value. Lets us test whether system-tax / dev-fit effects
  are pitch-type-specific (e.g. Houston's curveball install vs LAD sweeper).
- ``statcast_outs_above_average``: defensive runs prevented per (player, position,
  year). Lets us decompose "LAD inflates production" into offensive vs
  defensive contributions.

Catcher framing (``pybaseball.statcast_catcher_framing``) was probed but
fails CSV-parsing on Savant's response; deferred.

Statcast era: 2015+. Same era cap as our existing Statcast tables.
"""

# pyright: reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from savage_trade_evaluator.storage import db, schemas

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)
SOURCE = "baseball-savant"

# OAA positions to ingest. Savant supports OF + each infield position.
OAA_POSITIONS: tuple[str, ...] = ("OF", "3B", "SS", "2B", "1B")


def _safe_float(v: Any) -> float | None:
    """Coerce Savant string-or-NaN to float."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    import math

    if math.isnan(f):
        return None
    return f


def ingest_batter_percentile_ranks_year(year: int) -> int:
    """Pull batter percentile ranks for one year and upsert."""
    from pybaseball import statcast_batter_percentile_ranks

    df = statcast_batter_percentile_ranks(year)
    if df.empty:
        logger.warning("batter percentile ranks empty for %d", year)
        return 0

    rows: list[dict[str, Any]] = []
    for r in df.itertuples(index=False):
        rows.append(
            {
                "player_id": int(r.player_id),
                "player_name": getattr(r, "player_name", None),
                "year": int(r.year),
                "xwoba": _safe_float(getattr(r, "xwoba", None)),
                "xba": _safe_float(getattr(r, "xba", None)),
                "xslg": _safe_float(getattr(r, "xslg", None)),
                "xiso": _safe_float(getattr(r, "xiso", None)),
                "xobp": _safe_float(getattr(r, "xobp", None)),
                "brl": _safe_float(getattr(r, "brl", None)),
                "brl_percent": _safe_float(getattr(r, "brl_percent", None)),
                "exit_velocity": _safe_float(getattr(r, "exit_velocity", None)),
                "max_ev": _safe_float(getattr(r, "max_ev", None)),
                "hard_hit_percent": _safe_float(getattr(r, "hard_hit_percent", None)),
                "k_percent": _safe_float(getattr(r, "k_percent", None)),
                "bb_percent": _safe_float(getattr(r, "bb_percent", None)),
                "whiff_percent": _safe_float(getattr(r, "whiff_percent", None)),
                "chase_percent": _safe_float(getattr(r, "chase_percent", None)),
                "arm_strength": _safe_float(getattr(r, "arm_strength", None)),
                "sprint_speed": _safe_float(getattr(r, "sprint_speed", None)),
                "oaa": _safe_float(getattr(r, "oaa", None)),
                "bat_speed": _safe_float(getattr(r, "bat_speed", None)),
                "squared_up_rate": _safe_float(getattr(r, "squared_up_rate", None)),
                "swing_length": _safe_float(getattr(r, "swing_length", None)),
                "source": SOURCE,
            }
        )

    with db.connect() as conn:
        schemas.initialize(conn)
        _upsert_batter_percentile_ranks(conn, rows)
    logger.info("ingested %d batter percentile rows for %d", len(rows), year)
    return len(rows)


def _upsert_batter_percentile_ranks(
    conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_bpr", df)
    try:
        conn.execute(
            "INSERT INTO statcast_batter_percentile_ranks "
            "(player_id, player_name, year, xwoba, xba, xslg, xiso, xobp, brl, "
            "brl_percent, exit_velocity, max_ev, hard_hit_percent, k_percent, "
            "bb_percent, whiff_percent, chase_percent, arm_strength, sprint_speed, "
            "oaa, bat_speed, squared_up_rate, swing_length, source) "
            "SELECT player_id, player_name, year, xwoba, xba, xslg, xiso, xobp, brl, "
            "brl_percent, exit_velocity, max_ev, hard_hit_percent, k_percent, "
            "bb_percent, whiff_percent, chase_percent, arm_strength, sprint_speed, "
            "oaa, bat_speed, squared_up_rate, swing_length, source "
            "FROM _staging_bpr "
            "ON CONFLICT (player_id, year) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_bpr")


def ingest_pitcher_arsenal_year(year: int, min_pa: int = 25) -> int:
    """Pull pitcher per-pitch-type arsenal stats for one year."""
    from pybaseball import statcast_pitcher_arsenal_stats

    df = statcast_pitcher_arsenal_stats(year, minPA=min_pa)
    if df.empty:
        return 0

    rows: list[dict[str, Any]] = []
    for r in df.itertuples(index=False):
        # `last_name, first_name` column has a comma; access via getattr
        full_name = getattr(r, "_0", None) or getattr(r, "last_name__first_name", None)
        rows.append(
            {
                "player_id": int(r.player_id),
                "player_name": full_name,
                "team_name": getattr(r, "team_name_alt", None),
                "year": year,
                "pitch_type": str(r.pitch_type),
                "pitch_name": getattr(r, "pitch_name", None),
                "run_value_per_100": _safe_float(getattr(r, "run_value_per_100", None)),
                "run_value": _safe_float(getattr(r, "run_value", None)),
                "pitches": int(r.pitches) if r.pitches else None,
                "pitch_usage": _safe_float(getattr(r, "pitch_usage", None)),
                "pa": int(r.pa) if r.pa else None,
                "ba": _safe_float(getattr(r, "ba", None)),
                "slg": _safe_float(getattr(r, "slg", None)),
                "woba": _safe_float(getattr(r, "woba", None)),
                "whiff_percent": _safe_float(getattr(r, "whiff_percent", None)),
                "k_percent": _safe_float(getattr(r, "k_percent", None)),
                "put_away": _safe_float(getattr(r, "put_away", None)),
                "est_ba": _safe_float(getattr(r, "est_ba", None)),
                "est_slg": _safe_float(getattr(r, "est_slg", None)),
                "est_woba": _safe_float(getattr(r, "est_woba", None)),
                "hard_hit_percent": _safe_float(getattr(r, "hard_hit_percent", None)),
                "source": SOURCE,
            }
        )

    with db.connect() as conn:
        schemas.initialize(conn)
        _upsert_pitcher_arsenal(conn, rows)
    logger.info("ingested %d pitcher-arsenal rows for %d", len(rows), year)
    return len(rows)


def _upsert_pitcher_arsenal(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_par", df)
    try:
        conn.execute(
            "INSERT INTO statcast_pitcher_arsenal_stats "
            "(player_id, player_name, team_name, year, pitch_type, pitch_name, "
            "run_value_per_100, run_value, pitches, pitch_usage, pa, ba, slg, woba, "
            "whiff_percent, k_percent, put_away, est_ba, est_slg, est_woba, "
            "hard_hit_percent, source) "
            "SELECT player_id, player_name, team_name, year, pitch_type, pitch_name, "
            "run_value_per_100, run_value, pitches, pitch_usage, pa, ba, slg, woba, "
            "whiff_percent, k_percent, put_away, est_ba, est_slg, est_woba, "
            "hard_hit_percent, source "
            "FROM _staging_par "
            "ON CONFLICT (player_id, year, pitch_type) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_par")


def ingest_oaa_year(year: int) -> int:
    """Pull OAA across all infield + OF positions for one year."""
    from pybaseball import statcast_outs_above_average

    total = 0
    all_rows: list[dict[str, Any]] = []
    for pos in OAA_POSITIONS:
        try:
            df = statcast_outs_above_average(year, pos)
        except Exception as exc:
            logger.warning("OAA fetch failed for year=%d pos=%s: %s", year, pos, exc)
            continue
        if df.empty:
            continue
        for r in df.itertuples(index=False):
            all_rows.append(
                {
                    "player_id": int(r.player_id),
                    "player_name": getattr(r, "_0", None),
                    "team_name": getattr(r, "display_team_name", None),
                    "year": int(r.year),
                    "primary_pos": pos,
                    "fielding_runs_prevented": _safe_float(
                        getattr(r, "fielding_runs_prevented", None)
                    ),
                    "oaa": _safe_float(getattr(r, "outs_above_average", None)),
                    "oaa_infront": _safe_float(getattr(r, "outs_above_average_infront", None)),
                    "oaa_lateral_toward3b": _safe_float(
                        getattr(r, "outs_above_average_lateral_toward3bline", None)
                    ),
                    "oaa_lateral_toward1b": _safe_float(
                        getattr(r, "outs_above_average_lateral_toward1bline", None)
                    ),
                    "oaa_behind": _safe_float(getattr(r, "outs_above_average_behind", None)),
                    "oaa_rhh": _safe_float(getattr(r, "outs_above_average_rhh", None)),
                    "oaa_lhh": _safe_float(getattr(r, "outs_above_average_lhh", None)),
                    "actual_success_rate": _safe_float(
                        getattr(r, "actual_success_rate_formatted", None)
                    ),
                    "adj_estimated_success_rate": _safe_float(
                        getattr(r, "adj_estimated_success_rate_formatted", None)
                    ),
                    "diff_success_rate": _safe_float(
                        getattr(r, "diff_success_rate_formatted", None)
                    ),
                    "source": SOURCE,
                }
            )
        total += len(df)

    with db.connect() as conn:
        schemas.initialize(conn)
        _upsert_oaa(conn, all_rows)
    logger.info(
        "ingested %d OAA rows for %d (across %d positions)", len(all_rows), year, len(OAA_POSITIONS)
    )
    return len(all_rows)


def _upsert_oaa(conn: duckdb.DuckDBPyConnection, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    import pandas as pd

    df = pd.DataFrame(rows)
    conn.register("_staging_oaa", df)
    try:
        conn.execute(
            "INSERT INTO statcast_outs_above_average "
            "(player_id, player_name, team_name, year, primary_pos, "
            "fielding_runs_prevented, oaa, oaa_infront, oaa_lateral_toward3b, "
            "oaa_lateral_toward1b, oaa_behind, oaa_rhh, oaa_lhh, "
            "actual_success_rate, adj_estimated_success_rate, diff_success_rate, source) "
            "SELECT player_id, player_name, team_name, year, primary_pos, "
            "fielding_runs_prevented, oaa, oaa_infront, oaa_lateral_toward3b, "
            "oaa_lateral_toward1b, oaa_behind, oaa_rhh, oaa_lhh, "
            "actual_success_rate, adj_estimated_success_rate, diff_success_rate, source "
            "FROM _staging_oaa "
            "ON CONFLICT (player_id, year, primary_pos) DO NOTHING"
        )
    finally:
        conn.unregister("_staging_oaa")


def ingest_all_for_year(year: int) -> dict[str, int]:
    """Ingest all three Statcast-extended sources for one year."""
    return {
        "batter_percentile": ingest_batter_percentile_ranks_year(year),
        "pitcher_arsenal": ingest_pitcher_arsenal_year(year),
        "oaa": ingest_oaa_year(year),
    }


def ingest_range(start: int, end: int) -> dict[str, int]:
    """Ingest all three Statcast-extended sources across a year range."""
    totals = {"batter_percentile": 0, "pitcher_arsenal": 0, "oaa": 0}
    for year in range(start, end + 1):
        result = ingest_all_for_year(year)
        for k, v in result.items():
            totals[k] += v
    return totals
