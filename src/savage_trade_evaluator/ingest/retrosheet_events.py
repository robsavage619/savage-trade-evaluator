"""Retrosheet play-by-play event log ingestion.

Parses Retrosheet .EVA (AL) and .EVN (NL) event files into three derived
tables that unlock the leverage-deployment and platoon-deployment features.

Data source: https://www.retrosheet.org/game.htm
Download: season event files (e.g. 2015EVA.zip, 2015EVN.zip)
Unzip to a local directory and pass the path to ingest().

Tables produced:
  retrosheet_game_appearances — one row per pitcher appearance per game
    (team, season, game_id, pitcher_id, is_reliever, n_batters_faced,
     avg_li, leverage_ge_1_5_pct, leverage_lt_0_7_pct)

  retrosheet_pa_matchups — one row per plate appearance
    (team, season, game_id, bat_hand, pit_hand, event_cd, runs_scored)

Schema version bump required — add SCHEMA_VERSION bump in storage/schemas.py
and DDL for both tables.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

import pandas as pd

from savage_trade_evaluator.storage import db

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SOURCE = "retrosheet"

# ---------------------------------------------------------------------------
# Column indices (0-based) in the standard Retrosheet event file format.
# Reference: retrosheet.org/datause.html / Chadwick output column order.
# ---------------------------------------------------------------------------
COL_GAME_ID = 0
COL_VISITING_TEAM = 1
COL_INN_CT = 2
COL_INN_HALF = 3  # 0=top (visitor bats), 1=bottom (home bats)
COL_OUTS_CT = 5
COL_BALLS_CT = 6
COL_STRIKES_CT = 7
COL_BAT_HAND_CD = 10
COL_RESP_BAT_ID = 11
COL_RESP_BAT_HAND_CD = 12
COL_RESP_PIT_ID = 13
COL_RESP_PIT_HAND_CD = 14
COL_EVENT_CD = 34
COL_EVENT_RUNS_CT = 58
COL_BASE1_RUN_ID = 83
COL_BASE2_RUN_ID = 84
COL_BASE3_RUN_ID = 85

# Minimum column count — rows shorter than this are malformed and skipped.
MIN_COLS = 86

# Events that constitute a completed plate appearance (not just baserunning).
# Reference: retrosheet.org/eventfile.htm
PA_EVENT_CODES = frozenset({
    2,   # Generic out
    3,   # Strikeout
    14,  # Walk
    15,  # Intentional walk
    16,  # Hit by pitch
    20,  # Single
    21,  # Double
    22,  # Triple
    23,  # Home run
    24,  # Other advance / balk (counts some PA)
})

# ---------------------------------------------------------------------------
# Simplified Leverage Index lookup table.
# Full Tango table has 288 entries (24 base states × 3 outs × 9 half-innings ×
# 2 halves × run differentials). This is a 10-entry sample for early innings
# that captures the ordering. The full version should be loaded from a CSV;
# this approximation is sufficient for the feature-signal we need (hi/lo LI
# classification), not for exact win-probability models.
#
# Keys: (inning, half, outs, base_state)
#   inning: 1-9+ (clipped to 9 for extra innings)
#   half: 0=top, 1=bottom
#   outs: 0, 1, 2
#   base_state: bitmask — bit0=1B, bit1=2B, bit2=3B (0=bases empty, 7=loaded)
# Values: base leverage index (before run-diff scaling)
# ---------------------------------------------------------------------------
_LI_SAMPLE: dict[tuple[int, int, int, int], float] = {
    # Late innings, high leverage
    (9, 1, 0, 0): 2.00,   # Bot 9, 0 out, bases empty
    (9, 1, 0, 3): 3.50,   # Bot 9, 0 out, 1B+2B
    (9, 1, 1, 1): 2.50,   # Bot 9, 1 out, runner on 1B
    (9, 1, 2, 3): 3.80,   # Bot 9, 2 out, 1B+2B
    (8, 1, 2, 1): 2.10,   # Bot 8, 2 out, runner on 1B
    # Mid-innings, moderate leverage
    (7, 1, 0, 0): 1.20,
    (7, 1, 1, 3): 1.80,
    # Early innings, low leverage
    (1, 0, 0, 0): 0.50,
    (2, 0, 0, 0): 0.55,
    (3, 0, 1, 0): 0.65,
}

# Scaling factor applied per run-differential unit away from 0.
# A 3-run lead roughly halves LI; a 3-run deficit also lowers it.
_RUN_DIFF_DECAY = 0.18


def compute_leverage_index(
    inning: int,
    half: int,
    outs: int,
    base_state: int,
    run_diff: int,
) -> float:
    """Compute a simplified leverage index (Tango approximation).

    Uses a precomputed lookup table for the (inning, half, outs, base_state)
    component, then scales by run differential. This is an approximation
    suitable for high/low LI classification, not for exact win-probability
    models.

    Args:
        inning: Current inning (1-indexed; capped at 9 internally).
        half: 0 = top (visitor batting), 1 = bottom (home batting).
        outs: Outs recorded before the play (0, 1, or 2).
        base_state: Bitmask of occupied bases (bit0=1B, bit1=2B, bit2=3B).
        run_diff: Batting team's run differential at the start of the play
            (positive = batting team leading).

    Returns:
        Estimated leverage index (≥ 0.0).
    """
    inn_key = min(inning, 9)
    base_li = _LI_SAMPLE.get((inn_key, half, outs, base_state))

    if base_li is None:
        # Fallback: scale from a neutral-situation estimate that rises with
        # inning and base occupancy.
        base_li = 0.4 + (inn_key - 1) * 0.15 + bin(base_state).count("1") * 0.2

    # Each run of separation decays leverage multiplicatively.
    diff_penalty = _RUN_DIFF_DECAY * abs(run_diff)
    li = base_li * max(0.05, 1.0 - diff_penalty)
    return round(li, 3)


def parse_event_file(path: Path) -> Iterator[dict]:
    """Parse a single Retrosheet event file (.EVA or .EVN) into dicts.

    Retrosheet event files have no header row. Column positions follow the
    standard Chadwick output order documented at retrosheet.org/datause.html.
    Each yielded dict contains only the fields needed for leverage-deployment
    and platoon-deployment feature derivation.

    Args:
        path: Path to a plain-text Retrosheet event file.

    Yields:
        One dict per play-by-play row with keys:
            game_id, visiting_team, inning, half, outs, bat_hand,
            resp_bat_id, resp_bat_hand, resp_pit_id, resp_pit_hand,
            event_cd, event_runs_ct, base1_run_id, base2_run_id,
            base3_run_id, base_state.
    """
    with path.open(encoding="latin-1", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) < MIN_COLS:
                continue
            try:
                base_state = (
                    (1 if row[COL_BASE1_RUN_ID].strip() else 0)
                    | (2 if row[COL_BASE2_RUN_ID].strip() else 0)
                    | (4 if row[COL_BASE3_RUN_ID].strip() else 0)
                )
                yield {
                    "game_id": row[COL_GAME_ID].strip(),
                    "visiting_team": row[COL_VISITING_TEAM].strip(),
                    "inning": int(row[COL_INN_CT]),
                    "half": int(row[COL_INN_HALF]),
                    "outs": int(row[COL_OUTS_CT]),
                    "bat_hand": row[COL_BAT_HAND_CD].strip(),
                    "resp_bat_id": row[COL_RESP_BAT_ID].strip(),
                    "resp_bat_hand": row[COL_RESP_BAT_HAND_CD].strip(),
                    "resp_pit_id": row[COL_RESP_PIT_ID].strip(),
                    "resp_pit_hand": row[COL_RESP_PIT_HAND_CD].strip(),
                    "event_cd": int(row[COL_EVENT_CD]),
                    "event_runs_ct": int(row[COL_EVENT_RUNS_CT] or 0),
                    "base1_run_id": row[COL_BASE1_RUN_ID].strip(),
                    "base2_run_id": row[COL_BASE2_RUN_ID].strip(),
                    "base3_run_id": row[COL_BASE3_RUN_ID].strip(),
                    "base_state": base_state,
                }
            except (ValueError, IndexError):
                logger.debug("skipping malformed event row in %s", path.name)
                continue


def _extract_event_files(zip_path: Path) -> list[Path]:
    """Extract .EVA / .EVN files from a zip into a sibling temp directory.

    Args:
        zip_path: Path to a Retrosheet season zip (e.g. 2015EVA.zip).

    Returns:
        List of extracted event file paths.
    """
    out_dir = zip_path.parent / zip_path.stem
    out_dir.mkdir(exist_ok=True)
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            upper = name.upper()
            if upper.endswith(".EVA") or upper.endswith(".EVN"):
                dest = out_dir / name
                if not dest.exists():
                    zf.extract(name, out_dir)
                extracted.append(dest)
    return extracted


# ---------------------------------------------------------------------------
# Per-game state tracker used while building appearance aggregates.
# ---------------------------------------------------------------------------

class _GameState:
    """Accumulates per-pitcher, per-game stats across event rows."""

    def __init__(self) -> None:
        # game_id → home_team (extracted from GAME_ID format: TMM{YYYYMMDD}{N})
        self.game_home: dict[str, str] = {}
        # (game_id, pit_id) → list of LI values per PA
        self.pit_lis: dict[tuple[str, str], list[float]] = defaultdict(list)
        # (game_id, pit_id) → n_batters_faced
        self.pit_pa: dict[tuple[str, str], int] = defaultdict(int)
        # (game_id, pit_id) → first_inn seen (1=starter if inn==1 and pa>0)
        self.pit_first_inn: dict[tuple[str, str], int] = {}

    def update(
        self,
        row: dict,
        li: float,
        visiting_team: str,
        home_team: str,
    ) -> None:
        """Incorporate one play-by-play row."""
        game_id = row["game_id"]
        if game_id not in self.game_home:
            self.game_home[game_id] = home_team

        pit_id = row["resp_pit_id"]
        if not pit_id:
            return
        key = (game_id, pit_id)
        if row["event_cd"] in PA_EVENT_CODES:
            self.pit_lis[key].append(li)
            self.pit_pa[key] += 1
            if key not in self.pit_first_inn:
                self.pit_first_inn[key] = row["inning"]

    def to_appearance_rows(self, season: int) -> list[dict]:
        """Collapse per-(game, pitcher) accumulators into appearance dicts."""
        rows: list[dict] = []
        for (game_id, pit_id), lis in self.pit_lis.items():
            home_team = self.game_home.get(game_id, "UNK")
            n_pa = self.pit_pa[(game_id, pit_id)]
            first_inn = self.pit_first_inn.get((game_id, pit_id), 99)
            is_reliever = first_inn > 1
            avg_li = sum(lis) / len(lis) if lis else 0.0
            pct_ge_1_5 = sum(1 for v in lis if v >= 1.5) / len(lis) if lis else 0.0
            pct_lt_0_7 = sum(1 for v in lis if v < 0.7) / len(lis) if lis else 0.0
            rows.append({
                "team": home_team,
                "season": season,
                "game_id": game_id,
                "pitcher_id": pit_id,
                "is_reliever": is_reliever,
                "n_batters_faced": n_pa,
                "avg_li": round(avg_li, 4),
                "leverage_ge_1_5_pct": round(pct_ge_1_5, 4),
                "leverage_lt_0_7_pct": round(pct_lt_0_7, 4),
            })
        return rows


def _process_event_file(
    path: Path,
    season: int,
    game_state: _GameState,
    pa_rows: list[dict],
) -> None:
    """Parse one event file, appending to game_state and pa_rows in-place.

    Args:
        path: Path to a .EVA or .EVN file.
        season: Calendar year (used for row tagging).
        game_state: Mutable appearance accumulator.
        pa_rows: List to append plate-appearance dicts to.
    """
    # game_id format: TMM{YYYYMMDD}{N} where TMM is the home-team Retrosheet code.
    run_scores: dict[str, int] = defaultdict(int)  # game_id → cumulative runs per half

    for row in parse_event_file(path):
        game_id = row["game_id"]
        home_team = game_id[:3]  # first 3 chars of GAME_ID = home team Retro code
        visiting_team = row["visiting_team"]

        # Batting team is visiting if half==0, home if half==1.
        batting_team = visiting_team if row["half"] == 0 else home_team
        fielding_team = home_team if row["half"] == 0 else visiting_team

        # Run differential from batting team's perspective.
        half_key = f"{game_id}_{row['half']}"
        run_diff = run_scores.get(f"{game_id}_bat", 0) - run_scores.get(f"{game_id}_field", 0)

        li = compute_leverage_index(
            inning=row["inning"],
            half=row["half"],
            outs=row["outs"],
            base_state=row["base_state"],
            run_diff=run_diff,
        )

        game_state.update(row, li, visiting_team, home_team)

        # Accumulate runs for subsequent LI calculations.
        run_scores[f"{game_id}_bat"] += row["event_runs_ct"]

        # Record PA-level matchup row (fielding team = pitcher's team).
        if row["event_cd"] in PA_EVENT_CODES:
            bat_hand = row["bat_hand"] or row["resp_bat_hand"]
            pit_hand = row["resp_pit_hand"]
            if bat_hand in ("L", "R") and pit_hand in ("L", "R"):
                pa_rows.append({
                    "team": fielding_team,
                    "season": season,
                    "game_id": game_id,
                    "bat_hand": bat_hand,
                    "pit_hand": pit_hand,
                    "event_cd": row["event_cd"],
                    "runs_scored": row["event_runs_ct"],
                })


def ingest(event_dir: Path, seasons: list[int] | None = None) -> int:
    """Ingest Retrosheet event files from a local directory into DuckDB.

    Walks ``event_dir`` for ``{season}EVA.zip`` and ``{season}EVN.zip``
    files, extracts .EVA/.EVN event files, parses each, aggregates to
    ``retrosheet_game_appearances`` and ``retrosheet_pa_matchups``, and
    upserts into DuckDB.

    Data must be downloaded manually from retrosheet.org/game.htm before
    calling this function. No network requests are made here.

    Args:
        event_dir: Local directory containing Retrosheet event ZIPs.
        seasons: List of seasons to ingest. If None, all ZIPs found are
            ingested.

    Returns:
        Total rows written across both tables.
    """
    zips = sorted(event_dir.glob("*EV?.zip"))
    if seasons is not None:
        season_set = {str(s) for s in seasons}
        zips = [z for z in zips if z.name[:4] in season_set]

    if not zips:
        logger.warning("no Retrosheet event ZIPs found in %s", event_dir)
        return 0

    total_rows = 0

    with db.connect() as conn:
        for zip_path in zips:
            season_str = zip_path.name[:4]
            try:
                season = int(season_str)
            except ValueError:
                logger.warning("could not parse season from filename %s, skipping", zip_path.name)
                continue

            logger.info("processing %s", zip_path.name)
            event_files = _extract_event_files(zip_path)
            if not event_files:
                logger.warning("no event files found in %s", zip_path.name)
                continue

            game_state = _GameState()
            pa_rows: list[dict] = []

            for ef in event_files:
                logger.debug("  parsing %s", ef.name)
                _process_event_file(ef, season, game_state, pa_rows)

            appearance_rows = game_state.to_appearance_rows(season)

            # Upsert appearance rows.
            if appearance_rows:
                app_df = pd.DataFrame(appearance_rows)
                conn.execute("""
                    INSERT OR REPLACE INTO retrosheet_game_appearances
                        (team, season, game_id, pitcher_id, is_reliever,
                         n_batters_faced, avg_li, leverage_ge_1_5_pct,
                         leverage_lt_0_7_pct, source, ingested_at)
                    SELECT
                        team, season, game_id, pitcher_id, is_reliever,
                        n_batters_faced, avg_li, leverage_ge_1_5_pct,
                        leverage_lt_0_7_pct,
                        'retrosheet', CURRENT_TIMESTAMP
                    FROM app_df
                """)
                total_rows += len(appearance_rows)

            # Upsert PA matchup rows.
            if pa_rows:
                pa_df = pd.DataFrame(pa_rows)
                conn.execute("""
                    INSERT INTO retrosheet_pa_matchups
                        (team, season, game_id, bat_hand, pit_hand,
                         event_cd, runs_scored, source, ingested_at)
                    SELECT
                        team, season, game_id, bat_hand, pit_hand,
                        event_cd, runs_scored,
                        'retrosheet', CURRENT_TIMESTAMP
                    FROM pa_df
                """)
                total_rows += len(pa_rows)

            logger.info(
                "season %d: %d appearance rows, %d PA matchup rows",
                season,
                len(appearance_rows),
                len(pa_rows),
            )

    return total_rows


def derive_team_season_leverage_features() -> pd.DataFrame:
    """Query retrosheet_game_appearances and return team-season leverage metrics.

    Filters to reliever appearances only, then computes per-(team, season)
    weighted averages of leverage-deployment rates.

    Returns:
        DataFrame with columns:
            bref_code, season, reliever_leverage_ge_1_5_pct,
            reliever_leverage_lt_0_7_pct.
        One row per (team, season).
    """
    sql = """
        SELECT
            team                                        AS bref_code,
            season,
            round(avg(leverage_ge_1_5_pct), 4)         AS reliever_leverage_ge_1_5_pct,
            round(avg(leverage_lt_0_7_pct), 4)         AS reliever_leverage_lt_0_7_pct
        FROM retrosheet_game_appearances
        WHERE is_reliever = TRUE
          AND n_batters_faced >= 1
        GROUP BY team, season
        ORDER BY season, team
    """
    with db.connect(read_only=True) as conn:
        return conn.execute(sql).df()


def derive_team_season_platoon_features() -> pd.DataFrame:
    """Compute per-(team, season) wOBA split by same-hand vs. opposite-hand matchup.

    wOBA approximation uses linear weights on event codes (out=0, walk=0.69,
    HBP=0.72, single=0.89, double=1.27, triple=1.62, HR=2.10).
    The platoon differential is (opposite-hand wOBA) − (same-hand wOBA).
    A positive differential means the team exploits platoon advantages well.

    Returns:
        DataFrame with columns:
            bref_code, season, same_hand_woba, opp_hand_woba,
            platoon_woba_diff.
        One row per (team, season).
    """
    sql = """
        WITH weights AS (
            SELECT
                team,
                season,
                -- same-hand matchup (pitcher/batter same side = pitcher advantage)
                CASE
                    WHEN bat_hand = pit_hand THEN 'same'
                    ELSE 'opp'
                END                                                      AS matchup,
                CASE event_cd
                    WHEN 14 THEN 0.69   -- walk
                    WHEN 15 THEN 0.69   -- IBB (treat same as walk)
                    WHEN 16 THEN 0.72   -- HBP
                    WHEN 20 THEN 0.89   -- single
                    WHEN 21 THEN 1.27   -- double
                    WHEN 22 THEN 1.62   -- triple
                    WHEN 23 THEN 2.10   -- HR
                    ELSE 0.00
                END                                                      AS woba_val
            FROM retrosheet_pa_matchups
        ),
        agg AS (
            SELECT
                team,
                season,
                matchup,
                round(avg(woba_val), 4) AS woba
            FROM weights
            GROUP BY team, season, matchup
        )
        SELECT
            same_side.team          AS bref_code,
            same_side.season,
            same_side.woba          AS same_hand_woba,
            opp_side.woba           AS opp_hand_woba,
            round(opp_side.woba - same_side.woba, 4) AS platoon_woba_diff
        FROM agg same_side
        JOIN agg opp_side
            ON same_side.team = opp_side.team
           AND same_side.season = opp_side.season
           AND same_side.matchup = 'same'
           AND opp_side.matchup = 'opp'
        ORDER BY season, bref_code
    """
    with db.connect(read_only=True) as conn:
        return conn.execute(sql).df()
