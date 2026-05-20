"""Retrosheet play-by-play event log ingestion.

Parses native Retrosheet .EVA (AL) and .EVN (NL) event files into two derived
tables that unlock the leverage-deployment and platoon-deployment features.

Data source: https://www.retrosheet.org/game.htm
Download: combined season event ZIPs (e.g. 2015EVE.zip) from
  https://www.retrosheet.org/events/<year>eve.zip
Each zip contains per-team .EVA / .EVN files and .ROS roster files.

Native format (NOT Chadwick CSV output):
  id,<game_id>              → starts a new game
  info,visteam,<code>       → visiting team code
  start,<id>,<name>,<team_side(0/1)>,<bat_order>,<pos>  → starter
  sub,<id>,<name>,<team_side>,<bat_order>,<pos>          → substitution
  play,<inn>,<half>,<bat_id>,<count>,<pitches>,<event>   → plate appearance
  data,er,<pit_id>,<n>                                   → earned runs

Tables produced:
  retrosheet_game_appearances — one row per pitcher appearance per game
  retrosheet_pa_matchups — one row per plate appearance
"""

from __future__ import annotations

import logging
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Iterator

import pandas as pd

from savage_trade_evaluator.storage import db

logger = logging.getLogger(__name__)

SOURCE = "retrosheet"

# ---------------------------------------------------------------------------
# Events that constitute a completed plate appearance (not just baserunning).
# ---------------------------------------------------------------------------
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
})

# Standalone record types that are NOT plate appearances (baserunning only).
_NON_PA_PREFIXES = frozenset({
    "BK", "CS", "DI", "OA", "PB", "PO", "POCS", "SB", "WP", "NP",
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


def _load_handedness(zip_path: Path) -> dict[str, dict[str, str]]:
    """Load player handedness from .ROS roster files inside a season zip.

    .ROS format: player_id,last,first,bat_hand,pit_hand,...

    Args:
        zip_path: Path to a Retrosheet season zip (e.g. 2015EVE.zip).

    Returns:
        Dict mapping player_id → {"bat_hand": "L"|"R"|"", "pit_hand": ...}.
    """
    result: dict[str, dict[str, str]] = {}
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if name.upper().endswith(".ROS"):
                    with zf.open(name) as fh:
                        for line in fh.read().decode("latin-1").splitlines():
                            parts = line.strip().split(",")
                            if len(parts) < 5:
                                continue
                            pid = parts[0].strip()
                            bat = parts[3].strip().upper()
                            pit = parts[4].strip().upper()
                            result[pid] = {
                                "bat_hand": bat if bat in ("L", "R") else "",
                                "pit_hand": pit if pit in ("L", "R") else "",
                            }
    except (zipfile.BadZipFile, OSError) as exc:
        logger.warning("could not load handedness from %s: %s", zip_path.name, exc)
    return result


def _parse_event_code(event_str: str) -> tuple[int, bool, int]:
    """Parse a Retrosheet native event description string.

    Args:
        event_str: The event field from a play record (e.g. "S7", "K", "HR/7").

    Returns:
        Tuple of (event_cd, is_pa, outs_recorded).
        event_cd: integer event code matching PA_EVENT_CODES conventions.
        is_pa: True if this event is a completed plate appearance.
        outs_recorded: 0, 1, 2, or 3 outs made on this play.
    """
    # Strip trailing whitespace and notes after '+' (multi-event plays handled below)
    raw = event_str.strip()

    # Split on '.' to separate advance codes; work with the play portion only.
    play_part = raw.split(".")[0]

    # Extract the base event type: everything before '/' (modifiers) or '+'.
    base = play_part.split("/")[0].split("+")[0].strip()

    # Non-PA baserunning events — match any suffix (SB2, CS3H, POCS2, etc.).
    for prefix in _NON_PA_PREFIXES:
        if base.startswith(prefix):
            return 0, False, 0

    # Double-play / triple-play modifier → extra outs.
    extra_outs = 0
    upper_raw = raw.upper()
    if "/TP" in upper_raw or "/GTP" in upper_raw:
        extra_outs = 2
    elif "/GDP" in upper_raw or "/DP" in upper_raw or "/LDP" in upper_raw or "/FDP" in upper_raw:
        extra_outs = 1

    # Home run variants.
    if base.startswith("HR") or base == "H":
        return 23, True, 0

    if base.startswith("T"):
        return 22, True, 0

    if base.startswith("D") and not base.startswith("DI"):
        return 21, True, 0

    if base.startswith("S") and not base.startswith("SB"):
        return 20, True, 0

    if base.startswith("HP"):
        return 16, True, 0

    if base.startswith("IW") or base == "I":
        return 15, True, 0

    if base.startswith("W") and not base.startswith("WP"):
        return 14, True, 0

    if base.startswith("K"):
        # Strikeout: batter still may reach on WP/PB/E (K+WP, K+PB).
        # Either way it is a PA and records 1 out (the K).
        return 3, True, 1 + extra_outs

    if base.startswith("FC"):
        # Fielder's choice — batter reaches, 1 out on the basepaths.
        return 2, True, 1 + extra_outs

    if base.startswith("E"):
        # Error — batter reaches, 0 outs (unless DP).
        return 2, True, extra_outs

    if base.startswith("C"):
        # Catcher's interference — batter reaches.
        return 2, True, extra_outs

    # Generic out (groundout, flyout, lineout, popup codes like "53", "F8", "L6", etc.).
    return 2, True, 1 + extra_outs


def parse_event_file(
    path: Path,
    handedness: dict[str, dict[str, str]] | None = None,
) -> Iterator[dict]:
    """Parse a single Retrosheet native event file (.EVA or .EVN).

    Handles the native Retrosheet event format (id/info/start/sub/play records),
    not Chadwick CSV output. Player handedness is resolved from the .ROS data
    bundled in the season zip; pass the result of _load_handedness() here.

    Args:
        path: Path to a native .EVA or .EVN event file.
        handedness: Dict from _load_handedness(). If None, bat/pit hand fields
            will be empty strings.

    Yields:
        One dict per completed plate appearance with keys:
            game_id, visiting_team, inning, half, outs, bat_hand,
            resp_bat_id, resp_bat_hand, resp_pit_id, resp_pit_hand,
            event_cd, event_runs_ct, base1_run_id, base2_run_id,
            base3_run_id, base_state.
    """
    if handedness is None:
        handedness = {}

    game_id = ""
    visiting_team = ""
    inning = 1
    half = 0
    outs = 0
    base1 = base2 = base3 = ""
    # Current pitcher indexed by fielding team side: "0"=visitor, "1"=home.
    cur_pitcher: dict[str, str] = {"0": "", "1": ""}

    try:
        lines = path.read_text(encoding="latin-1").splitlines()
    except OSError as exc:
        logger.warning("cannot read %s: %s", path.name, exc)
        return

    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split(",")
        rec = parts[0]

        if rec == "id":
            game_id = parts[1].strip() if len(parts) > 1 else ""
            # Retrosheet game_id: first 3 chars are home-team code.
            inning = 1
            half = 0
            outs = 0
            base1 = base2 = base3 = ""
            cur_pitcher = {"0": "", "1": ""}

        elif rec == "info":
            if len(parts) >= 3 and parts[1].strip() == "visteam":
                visiting_team = parts[2].strip()

        elif rec in ("start", "sub"):
            # format: start,player_id,name,team_side(0=vis/1=home),bat_order,position
            if len(parts) >= 6 and parts[5].strip() == "1":
                side = parts[3].strip()  # "0" or "1"
                cur_pitcher[side] = parts[1].strip()

        elif rec == "play":
            # play,inning,half,batter_id,count,pitches,event
            if len(parts) < 7:
                continue
            try:
                new_inn = int(parts[1])
                new_half = int(parts[2])
            except ValueError:
                continue

            # Reset outs and bases at each new half-inning.
            if (new_inn, new_half) != (inning, half):
                inning = new_inn
                half = new_half
                outs = 0
                base1 = base2 = base3 = ""

            batter_id = parts[3].strip()
            event_str = parts[6].strip() if len(parts) > 6 else ""
            if not event_str:
                continue

            try:
                event_cd, is_pa, n_outs = _parse_event_code(event_str)
            except Exception:
                logger.debug("unparseable event '%s' in %s", event_str, path.name)
                continue

            if not is_pa:
                continue

            # Fielding team is opposite of batting half.
            # half=0 → top → visitor bats → home (side "1") fields.
            fielding_side = "1" if half == 0 else "0"
            pit_id = cur_pitcher.get(fielding_side, "")

            pit_info = handedness.get(pit_id, {})
            bat_info = handedness.get(batter_id, {})
            pit_hand = pit_info.get("pit_hand", "")
            bat_hand = bat_info.get("bat_hand", "")

            base_state = (
                (1 if base1 else 0)
                | (2 if base2 else 0)
                | (4 if base3 else 0)
            )
            home_team = game_id[:3] if len(game_id) >= 3 else ""

            yield {
                "game_id": game_id,
                "visiting_team": visiting_team,
                "home_team": home_team,
                "inning": inning,
                "half": half,
                "outs": outs,
                "bat_hand": bat_hand,
                "resp_bat_id": batter_id,
                "resp_bat_hand": bat_hand,
                "resp_pit_id": pit_id,
                "resp_pit_hand": pit_hand,
                "event_cd": event_cd,
                "event_runs_ct": 0,
                "base1_run_id": base1,
                "base2_run_id": base2,
                "base3_run_id": base3,
                "base_state": base_state,
            }

            outs += n_outs
            if outs >= 3:
                outs = 0
                base1 = base2 = base3 = ""


def _extract_event_files(zip_path: Path) -> list[Path]:
    """Extract .EVA / .EVN files from a Retrosheet season zip.

    Handles both combined `{year}EVE.zip` (AL+NL) and separate
    `{year}EVA.zip` / `{year}EVN.zip` naming conventions.

    Args:
        zip_path: Path to a Retrosheet season zip.

    Returns:
        List of extracted event file paths.
    """
    out_dir = zip_path.parent / zip_path.stem
    out_dir.mkdir(exist_ok=True)
    extracted: list[Path] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                upper = name.upper()
                if upper.endswith(".EVA") or upper.endswith(".EVN"):
                    dest = out_dir / Path(name).name
                    if not dest.exists():
                        zf.extract(name, out_dir)
                        # ZipFile may create subdirectories; find the file.
                        extracted_dest = out_dir / name
                        if extracted_dest != dest and extracted_dest.exists():
                            extracted_dest.rename(dest)
                    extracted.append(dest)
    except zipfile.BadZipFile as exc:
        logger.error("bad zip %s: %s", zip_path.name, exc)
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
    handedness: dict[str, dict[str, str]] | None = None,
) -> None:
    """Parse one event file, appending to game_state and pa_rows in-place.

    Args:
        path: Path to a .EVA or .EVN file.
        season: Calendar year (used for row tagging).
        game_state: Mutable appearance accumulator.
        pa_rows: List to append plate-appearance dicts to.
        handedness: Player handedness dict from _load_handedness().
    """
    run_scores: dict[str, int] = defaultdict(int)

    for row in parse_event_file(path, handedness=handedness):
        game_id = row["game_id"]
        home_team = row["home_team"]
        visiting_team = row["visiting_team"]

        # half=0 → top (visitor bats); half=1 → bottom (home bats).
        fielding_team = home_team if row["half"] == 0 else visiting_team

        run_diff = run_scores.get(f"{game_id}_bat", 0) - run_scores.get(f"{game_id}_field", 0)

        li = compute_leverage_index(
            inning=row["inning"],
            half=row["half"],
            outs=row["outs"],
            base_state=row["base_state"],
            run_diff=run_diff,
        )

        game_state.update(row, li, visiting_team, home_team)
        run_scores[f"{game_id}_bat"] += row["event_runs_ct"]

        if row["event_cd"] in PA_EVENT_CODES:
            bat_hand = row["bat_hand"]
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
            handedness = _load_handedness(zip_path)
            logger.debug("  loaded handedness for %d players", len(handedness))
            event_files = _extract_event_files(zip_path)
            if not event_files:
                logger.warning("no event files found in %s", zip_path.name)
                continue

            game_state = _GameState()
            pa_rows: list[dict] = []

            for ef in event_files:
                logger.debug("  parsing %s", ef.name)
                _process_event_file(ef, season, game_state, pa_rows, handedness=handedness)

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


# Retrosheet uses legacy team codes for franchises that moved or have historical
# abbreviations. Map to Baseball Reference codes for the join in team_season_features.
_RETRO_TO_BREF: dict[str, str] = {
    "ANA": "LAA",   # Angels
    "CHA": "CHW",   # White Sox
    "CHN": "CHC",   # Cubs
    "KCA": "KCR",   # Royals
    "LAN": "LAD",   # Dodgers
    "NYA": "NYY",   # Yankees
    "NYN": "NYM",   # Mets
    "SDN": "SDP",   # Padres
    "SFN": "SFG",   # Giants
    "SLN": "STL",   # Cardinals
    "TBA": "TBR",   # Rays
    "WAS": "WSN",   # Nationals
}


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
        df = conn.execute(sql).df()
    df["bref_code"] = df["bref_code"].replace(_RETRO_TO_BREF)
    return df


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
        df = conn.execute(sql).df()
    df["bref_code"] = df["bref_code"].replace(_RETRO_TO_BREF)
    return df
