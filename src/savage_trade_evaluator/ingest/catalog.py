"""Stat-source catalog — a registry of every metric we know how to fetch.

The trade-eval thesis (D-01: context-aware valuation) does not pre-commit to
which outcome metric defines trade success. WAR is the default historical
spine, but the right outcome variable may turn out to be something else —
xwOBA delta, sprint speed retention, framing runs gained, dev-system-specific
arsenal stats, etc.

This catalog documents what we *can* ingest without committing us to ingesting
all of it. Each entry knows:

* the underlying source (MLB Stats API / Baseball Reference / Baseball Savant /
  Lahman / FanGraphs / manual)
* the granularity (player-season, player-season-stint, player-career,
  team-season, pitch-level)
* the era of availability (start year)
* the pybaseball function (or other client) that fetches it
* whether we have an active adapter in this project (``ingested=True``) or just
  scaffolded knowledge of its existence (``ingested=False``)

The ``CATALOG`` constant is the source of truth. ``docs/STATS_CATALOG.md``
mirrors it for human browsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Granularity = Literal[
    "player-season",
    "player-season-stint",
    "player-career",
    "player-game",
    "pitch-level",
    "batted-ball",
    "team-season",
    "team-game",
    "draft",
    "transaction",
    "standings",
    "reference",
]

Source = Literal[
    "mlb-stats-api",
    "bref-bwar",
    "bref-other",
    "baseball-savant",
    "fangraphs",
    "lahman",
    "retrosheet",
    "chadwick",
    "manual",
    "spotrac",
    "tjstats",
]


@dataclass(frozen=True, slots=True)
class StatSource:
    """One source-level entry in the catalog.

    Attributes:
        name: Short slug identifying the source.
        source: Underlying data provider.
        granularity: What each row represents.
        era_start: First year the source has data for.
        era_end: Last year (None if current).
        fetcher: pybaseball function path or other client reference.
        primary_columns: Key columns this source uniquely provides
            (not exhaustive — just the headline reasons to use it).
        target_table: DuckDB table we land it in, when ingested. ``None`` if
            not yet wired up.
        ingested: Whether we currently have a working adapter for this source.
        blocked: Whether this source is currently inaccessible (Cloudflare /
            paywall / etc.).
        notes: Free-text caveats.
    """

    name: str
    source: Source
    granularity: Granularity
    era_start: int
    era_end: int | None
    fetcher: str
    primary_columns: tuple[str, ...]
    target_table: str | None = None
    ingested: bool = False
    blocked: bool = False
    notes: str = ""


CATALOG: tuple[StatSource, ...] = (
    # === Transactions / trade structure ===
    StatSource(
        name="transactions",
        source="mlb-stats-api",
        granularity="transaction",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.transactions.fetch_season",
        primary_columns=(
            "transaction_id",
            "type_code",
            "date",
            "from_team_id",
            "to_team_id",
            "player_id",
        ),
        target_table="transactions",
        ingested=True,
        notes="Pre-2010 coverage is sparse (D-14). 2010+ is comprehensive.",
    ),
    StatSource(
        name="retrosheet-transactions",
        source="retrosheet",
        granularity="transaction",
        era_start=1880,
        era_end=2022,
        fetcher="savage_trade_evaluator.ingest.retrosheet_transactions.ingest",
        primary_columns=(
            "transaction_id",
            "date",
            "type_code",
            "from_team_id",
            "to_team_id",
            "player_id",
        ),
        target_table="transactions",
        ingested=True,
        notes=(
            "Pre-2010 trade fill via Retrosheet tranDB.zip. Player IDs bridged "
            "via Chadwick register. Transaction-IDs offset by 10^10 to avoid "
            "PK collision with MLB Stats API IDs. Source attribution = "
            "'retrosheet'. Adds ~4,500 affiliated trade events pre-2010."
        ),
    ),
    # === Personnel (managers, coaches, front-office) ===
    StatSource(
        name="coaches",
        source="mlb-stats-api",
        granularity="team-season",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.coaches.fetch_team_season",
        primary_columns=(
            "team_id",
            "season",
            "job_code",
            "job_title",
            "person_id",
            "person_name",
        ),
        target_table="coaches",
        ingested=True,
        notes=(
            "Per team-season coaching staff (manager + assistants). Direct "
            "fuel for coach-portability features (MVP Machine Ch 5)."
        ),
    ),
    StatSource(
        name="front-office",
        source="bref-other",
        granularity="team-season",
        era_start=1990,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.front_office.ingest_team_season",
        primary_columns=(
            "team_id",
            "season",
            "role",
            "person_name",
        ),
        target_table="front_office",
        ingested=True,
        notes=(
            "Per team-season front office: GM, President of Baseball Ops, "
            "Farm Director, Scouting Director. Source: BR team-season pages. "
            "Required for GM-behavior modeling (D-09 / Phase 3)."
        ),
    ),
    # === Player WAR + value components ===
    StatSource(
        name="bwar-batting",
        source="bref-bwar",
        granularity="player-season-stint",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.bwar_bat",
        primary_columns=(
            "WAR",
            "WAR_rep",
            "WAA",
            "runs_above_avg_off",
            "runs_above_avg_def",
            "PA",
            "G",
            "salary",
        ),
        target_table="bwar_batting",
        ingested=True,
        notes="The historical spine. Multi-stint structure lets us split WAR by trade.",
    ),
    StatSource(
        name="bwar-pitching",
        source="bref-bwar",
        granularity="player-season-stint",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.bwar_pitch",
        primary_columns=("WAR", "WAR_rep", "WAA", "ERA_plus", "G", "GS", "BIP", "salary"),
        target_table="bwar_pitching",
        ingested=True,
        notes="Pitcher equivalent. Includes ERA+ as the park-adjusted rate-stat.",
    ),
    # === Statcast expected stats (luck-adjusted baselines) ===
    StatSource(
        name="statcast-batting-expected",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_batter_expected_stats",
        primary_columns=("xwOBA", "xBA", "xSLG", "wOBA", "BA", "SLG"),
        target_table="statcast_batting_expected",
        ingested=True,
        notes="x-stats are the regression-to-mean baseline (xwOBA filters out BABIP noise).",
    ),
    StatSource(
        name="statcast-pitching-expected",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_pitcher_expected_stats",
        primary_columns=("xwOBA", "xBA", "xSLG", "xERA", "ERA"),
        target_table="statcast_pitching_expected",
        ingested=True,
        notes="xERA is the FIP-equivalent we use in place of FanGraphs FIP.",
    ),
    StatSource(
        name="statcast-pitcher-percentile-ranks",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_pitcher_percentile_ranks",
        primary_columns=(
            "fb_velocity",
            "fb_spin",
            "curve_spin",
            "k_percent",
            "bb_percent",
            "whiff_percent",
            "chase_percent",
            "hard_hit_percent",
            "arm_strength",
        ),
        target_table="statcast_pitcher_percentile_ranks",
        ingested=True,
        notes="The arsenal data — direct fuel for dev-system-fit features.",
    ),
    # === Statcast Statcast leaderboards we know exist but haven't pulled yet ===
    StatSource(
        name="statcast-batter-percentile-ranks",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_batter_percentile_ranks",
        primary_columns=("xwOBA", "xBA", "xSLG", "barrel_pct", "exit_velocity", "sprint_speed"),
        target_table="statcast_batter_percentile_ranks",
        ingested=True,
        notes="Batter-side equivalent. Pull when batter dev-fit features become load-bearing.",
    ),
    StatSource(
        name="statcast-batter-exitvelo-barrels",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_batter_exitvelo_barrels",
        primary_columns=("avg_hit_speed", "max_hit_speed", "barrel_batted_rate"),
        target_table=None,
        ingested=False,
        notes="Quality-of-contact detail beyond percentile ranks.",
    ),
    StatSource(
        name="statcast-pitcher-arsenal-stats",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_pitcher_arsenal_stats",
        primary_columns=(
            "pitch_type",
            "pitches_thrown",
            "pitch_pct",
            "ba",
            "slg",
            "woba",
            "whiff_pct",
        ),
        target_table="statcast_pitcher_arsenal_stats",
        ingested=True,
        notes=(
            "Per-pitch-type breakdown per pitcher-season. Reveals which pitches "
            "an org's dev system actually fixed."
        ),
    ),
    StatSource(
        name="statcast-pitcher-pitch-arsenal",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_pitcher_pitch_arsenal",
        primary_columns=(
            "pitch_type",
            "velocity",
            "spin_rate",
            "vertical_movement",
            "horizontal_movement",
        ),
        target_table=None,
        ingested=False,
        notes="Per-pitch movement profiles. The 'pitch-design' feature space directly.",
    ),
    StatSource(
        name="statcast-sprint-speed",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_sprint_speed",
        primary_columns=("sprint_speed", "competitive_runs"),
        target_table=None,
        ingested=False,
        notes="Baserunning-side dev signal.",
    ),
    StatSource(
        name="statcast-outs-above-average",
        source="baseball-savant",
        granularity="player-season",
        era_start=2016,
        era_end=None,
        fetcher="pybaseball.statcast_outs_above_average",
        primary_columns=("outs_above_average", "estimated_success_rate"),
        target_table="statcast_outs_above_average",
        ingested=True,
        notes="Modern defensive metric. Replaces UZR/DRS as Statcast's defensive WAR component.",
    ),
    StatSource(
        name="statcast-catcher-framing",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_catcher_framing",
        primary_columns=("runs_extra_strikes", "strike_rate"),
        target_table="statcast_catcher_framing",
        ingested=True,
        notes="Catcher-specific dev signal — receiving + pitch framing.",
    ),
    StatSource(
        name="statcast-catcher-poptime",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_catcher_poptime",
        primary_columns=("pop_time", "exchange_time", "arm_strength"),
        target_table=None,
        ingested=False,
        notes="Catcher throwing-to-second metrics.",
    ),
    StatSource(
        name="statcast-outfielder-jump",
        source="baseball-savant",
        granularity="player-season",
        era_start=2016,
        era_end=None,
        fetcher="pybaseball.statcast_outfielder_jump",
        primary_columns=("reaction", "burst", "route", "feet_covered"),
        target_table=None,
        ingested=False,
        notes="Outfielder dev signal — breakdown of how OAA gets earned.",
    ),
    # === Pitch-level raw Statcast ===
    StatSource(
        name="statcast-pitch-by-pitch",
        source="baseball-savant",
        granularity="pitch-level",
        era_start=2008,
        era_end=None,
        fetcher="pybaseball.statcast",
        primary_columns=(
            "pitch_type",
            "release_speed",
            "release_spin_rate",
            "pfx_x",
            "pfx_z",
            "plate_x",
            "plate_z",
            "launch_angle",
            "launch_speed",
            "estimated_woba",
        ),
        target_table=None,
        ingested=False,
        notes=(
            "Every pitch since 2008 (PITCHf/x). The base layer everything else aggregates from. "
            "VERY large — defer until we need a feature we can't get from leaderboards."
        ),
    ),
    # === Historical / Lahman ===
    StatSource(
        name="lahman-batting",
        source="lahman",
        granularity="player-season-stint",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.lahman.batting",
        primary_columns=("G", "AB", "H", "HR", "RBI", "SB", "BB", "SO"),
        target_table=None,
        ingested=False,
        blocked=True,
        notes=(
            "pybaseball's Lahman auto-fetch is broken (zip-file unzip error). "
            "Workaround: download Lahman CSVs manually."
        ),
    ),
    StatSource(
        name="lahman-pitching",
        source="lahman",
        granularity="player-season-stint",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.lahman.pitching",
        primary_columns=("G", "GS", "IP", "ERA", "K", "BB", "HR"),
        target_table=None,
        ingested=False,
        blocked=True,
        notes="Same auto-fetch issue as lahman-batting.",
    ),
    StatSource(
        name="lahman-salaries",
        source="lahman",
        granularity="player-season",
        era_start=1985,
        era_end=2016,
        fetcher="pybaseball.lahman.salaries",
        primary_columns=("salary",),
        target_table=None,
        ingested=False,
        blocked=True,
        notes="Lahman salaries stop at 2016. Cot's Contracts is more current.",
    ),
    # === Draft history ===
    StatSource(
        name="amateur-draft",
        source="bref-other",
        granularity="draft",
        era_start=1965,
        era_end=None,
        fetcher="pybaseball.amateur_draft",
        primary_columns=("Year", "Rnd", "Pick", "Tm", "Player", "Pos", "School", "WAR"),
        target_table="draft_picks",
        ingested=True,
        notes=(
            "Draft history - needed for position-class x source-class "
            "baselines (D-11). One year at a time."
        ),
    ),
    # === Team-level seasonal ===
    StatSource(
        name="team-batting-bref",
        source="bref-other",
        granularity="team-season",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.team_batting",
        primary_columns=("R", "RA", "W", "L", "wRC+", "BABIP"),
        target_table=None,
        ingested=False,
        notes="Team-level seasonal aggregate. Org-level dev-fit signals at this level too.",
    ),
    StatSource(
        name="team-pitching-bref",
        source="bref-other",
        granularity="team-season",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.team_pitching",
        primary_columns=("ERA", "WHIP", "K9", "BB9", "FIP"),
        target_table=None,
        ingested=False,
        notes="Team-pitching aggregate. Pair with team-batting for season-level org features.",
    ),
    StatSource(
        name="standings",
        source="bref-other",
        granularity="standings",
        era_start=2010,
        era_end=None,
        fetcher="pybaseball.standings",
        primary_columns=("Tm", "W", "L", "GB", "season"),
        target_table="standings",
        ingested=True,
        notes=(
            "Per-season standings. Needed for contention-window features and "
            "playoff probability backfill."
        ),
    ),
    # === Cross-source player ID lookup ===
    StatSource(
        name="chadwick-register",
        source="chadwick",
        granularity="player-career",
        era_start=1871,
        era_end=None,
        fetcher="pybaseball.chadwick_register",
        primary_columns=(
            "key_mlbam",
            "key_bbref",
            "key_fangraphs",
            "key_retro",
            "name_first",
            "name_last",
        ),
        target_table="chadwick_register",
        ingested=True,
        notes=(
            "Definitive player-ID bridge across all data sources. "
            "MLBAM ↔ Retro ↔ BRef ↔ Fangraphs ID cross-walk."
        ),
    ),
    # === Blocked sources ===
    StatSource(
        name="fangraphs-batting-leaders",
        source="fangraphs",
        granularity="player-season",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fangraphs_leaders.ingest_range",
        primary_columns=(
            "wRC+", "wOBA", "WAR", "wBsR", "Offense",
            "Defense", "Batting", "Fielding", "Positional",
        ),
        target_table="fangraphs_batting_leaders",
        ingested=True,
        blocked=False,
        notes=(
            "FanGraphs batting leaderboards. Cloudflare gate bypassed via Firecrawl "
            "stealth proxy hitting the /api/leaders/major-league/data endpoint "
            "(type=8 full bundle). Curated ~50-col subset: park-adjusted rates "
            "(wRC+/wOBA), component WAR, batted-ball, plate discipline. xMLBAMID "
            "stored as mlbam_id for direct bridging. Backfilled 2010-2024 "
            "(verified reachable back to 2005). Requires FIRECRAWL_API_KEY."
        ),
    ),
    StatSource(
        name="fangraphs-pitching-leaders",
        source="fangraphs",
        granularity="player-season",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fangraphs_leaders.ingest_range",
        primary_columns=("FIP", "xFIP", "SIERA", "WAR", "K%", "BB%", "GB%"),
        target_table="fangraphs_pitching_leaders",
        ingested=True,
        blocked=False,
        notes=(
            "FanGraphs pitching leaderboards. Same Firecrawl stealth bypass as "
            "batting. Curated subset: FIP/xFIP/SIERA, K-BB%, LOB%, batted-ball, "
            "FBv. Backfilled 2010-2024. Requires FIRECRAWL_API_KEY."
        ),
    ),
    StatSource(
        name="fangraphs-prospects",
        source="fangraphs",
        granularity="player-season",
        era_start=2017,
        era_end=2026,
        fetcher="savage_trade_evaluator.ingest.prospects.ingest_range",
        primary_columns=("fv", "risk", "eta", "fangraphs_player_id"),
        target_table="prospect_rankings",
        ingested=True,
        blocked=False,
        notes=(
            "FanGraphs The Board preseason top-100 FV grades (2017-2024). "
            "Accessible without login via Firecrawl stealth proxy. "
            "Scraped once with scripts/parse_fg_prospects.py → cached to "
            "data/prospect_fv_cache/fangraphs_{year}.csv. Joined to trades "
            "via normalized player-name match in trade_acquired_prospect_fv "
            "view. Features: receiver_acquired_avg_fv, receiver_acquired_max_fv."
        ),
    ),
    StatSource(
        name="baseball-america-prospect-rankings",
        source="manual",
        granularity="player-season",
        era_start=1980,
        era_end=None,
        fetcher="manual scrape / archive",
        primary_columns=("rank", "team", "season"),
        target_table=None,
        ingested=False,
        blocked=True,
        notes=(
            "BA top-100 lists. Public for top-30 most years; full top-100 "
            "archive requires subscription or archive.org."
        ),
    ),
    # === Contracts / payroll (Spotrac) ===
    StatSource(
        name="spotrac-player-contracts",
        source="spotrac",
        granularity="player-season",
        era_start=2011,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.spotrac.ingest_year",
        primary_columns=(
            "mlb_player_id",
            "team_bref",
            "season",
            "base_salary",
            "cap_hit",
            "signing_bonus",
            "status",
        ),
        target_table="spotrac_player_contracts",
        ingested=True,
        notes=(
            "Per-player-season cap_hit + status (Veteran / Pre-Arb / etc.). "
            "Source of empirical $/WAR curve. 17,352 rows; 98.4% mlb_id match."
        ),
    ),
    StatSource(
        name="spotrac-team-payroll",
        source="spotrac",
        granularity="team-season",
        era_start=2011,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.spotrac.ingest_year",
        primary_columns=("team_bref", "season", "total_payroll"),
        target_table="spotrac_team_payroll",
        ingested=True,
        notes="Total committed payroll per team-season. 449 rows.",
    ),
    # === Statcast aux ===
    StatSource(
        name="statcast-pitch-movement",
        source="baseball-savant",
        granularity="player-season",
        era_start=2015,
        era_end=None,
        fetcher="pybaseball.statcast_pitch_movement",
        primary_columns=(
            "pitch_type",
            "avg_speed",
            "movement_inches_x",
            "movement_inches_z",
            "percent_rank_diff_x",
        ),
        target_table="statcast_pitch_movement",
        ingested=True,
        notes="Per-pitcher × pitch-type velocity / break / percentiles. 17,553 rows.",
    ),
    # === MLB Stats API reference / awards / rosters ===
    StatSource(
        name="mlb-people",
        source="mlb-stats-api",
        granularity="player-career",
        era_start=1871,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fortification.ingest_people",
        primary_columns=(
            "mlb_player_id",
            "full_name",
            "bat_side",
            "throw_hand",
            "birth_country",
            "birth_date",
        ),
        target_table="mlb_people",
        ingested=True,
        notes="Player demographics + handedness + nationality. 23,617 profiles.",
    ),
    StatSource(
        name="mlb-awards",
        source="mlb-stats-api",
        granularity="player-season",
        era_start=1990,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fortification.ingest_awards",
        primary_columns=("player_id", "award_id", "season"),
        target_table="mlb_awards",
        ingested=True,
        notes="17 award types (MVP, Cy Young, ROY, AS, etc.). 1,733 rows.",
    ),
    StatSource(
        name="mlb-venues",
        source="mlb-stats-api",
        granularity="reference",
        era_start=1871,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fortification.ingest_venues",
        primary_columns=("venue_id", "name", "city", "state"),
        target_table="mlb_venues",
        ingested=True,
        notes="Park reference table from MLB Stats API. 1,646 venues.",
    ),
    StatSource(
        name="retrosheet-parks",
        source="retrosheet",
        granularity="reference",
        era_start=1871,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fortification.ingest_parks",
        primary_columns=("park_id", "name", "city", "state"),
        target_table="retrosheet_parks",
        ingested=True,
        notes="Historical park reference from Retrosheet. 260 parks.",
    ),
    StatSource(
        name="retrosheet-gamelogs",
        source="retrosheet",
        granularity="team-game",
        era_start=1990,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.retrosheet_gamelogs.ingest_year",
        primary_columns=(
            "date",
            "home_team",
            "away_team",
            "home_score",
            "away_score",
            "attendance",
            "park_id",
        ),
        target_table="game_logs",
        ingested=True,
        notes="Per-game logs 1990-2024. 80,798 games.",
    ),
    StatSource(
        name="retrosheet-events",
        source="retrosheet",
        granularity="player-game",
        era_start=1921,
        era_end=2024,
        fetcher="savage_trade_evaluator.ingest.retrosheet_events.ingest",
        primary_columns=(
            "game_id",
            "pitcher_id",
            "avg_li",
            "leverage_ge_1_5_pct",
            "bat_hand",
            "pit_hand",
            "event_cd",
        ),
        target_table="retrosheet_game_appearances",
        ingested=False,
        notes=(
            "Play-by-play event logs (.EVA / .EVN). Adapter scaffolded; "
            "data download pending (retrosheet.org/game.htm). Unlocks "
            "reliever leverage-deployment rate (#6) and platoon-deployment "
            "skill (#7) features. Download season ZIPs manually and pass "
            "the directory to ingest.retrosheet_events.ingest()."
        ),
    ),
    StatSource(
        name="team-40man-rosters",
        source="mlb-stats-api",
        granularity="team-season",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fortification.ingest_rosters",
        primary_columns=("team_id", "season", "mlb_player_id", "position"),
        target_table="team_rosters",
        ingested=True,
        notes="40-man roster snapshots per team-season. 22,549 rows.",
    ),
    StatSource(
        name="milb-player-stats",
        source="mlb-stats-api",
        granularity="player-season-stint",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.milb_stats.ingest_season",
        primary_columns=(
            "mlb_player_id", "season", "sport_id", "team_id", "group_name",
            "plate_appearances", "ops", "babip", "innings_pitched", "era",
            "strikeouts", "walks",
        ),
        target_table="milb_player_seasons",
        ingested=True,
        notes=(
            "Per (player, season, sport_id, team_id, group) MiLB hitting + "
            "pitching stats from MLB Stats API sportId={11,12,13,14}. Same "
            "MLBAM player_id as MLB stats — direct join. Backfilled 2010-2024."
        ),
    ),
    StatSource(
        name="team-season-stats",
        source="mlb-stats-api",
        granularity="team-season",
        era_start=2010,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.fortification.ingest_team_season_stats",
        primary_columns=("team_id", "season", "wins", "losses", "runs", "runs_allowed"),
        target_table="team_season_stats",
        ingested=True,
        notes="Per team-season aggregate stats. 1,350 rows.",
    ),
    # === TJStats (tjstats.ca, Thomas Nestico) — public WordPress JSON API ===
    StatSource(
        name="tjstats-top-prospects",
        source="tjstats",
        granularity="player-season",
        era_start=2026,
        era_end=None,
        fetcher="tjstats.ca/wp-json/tjstats/v1/rankings",
        primary_columns=("player_id", "rank_value", "name", "fv", "report"),
        target_table="tjstats_prospect_rankings",
        ingested=True,
        notes=(
            "Live top-100 MLB prospect rankings with FV grades + free-text "
            "scouting reports. player_id is MLBAM (no bridging needed). "
            "Replaces blocked FanGraphs FV grades for Phase 2+ forward predictions. "
            "Snapshot history is shallow — only goes back to early 2026 (3 versions). "
            "Use for forward 'evaluate-a-proposed-trade-today' mode, not the "
            "2010-2024 backtester."
        ),
    ),
    StatSource(
        name="tjstats-scout-pitchers",
        source="tjstats",
        granularity="player-career",
        era_start=2026,
        era_end=None,
        fetcher="tjstats.ca/wp-json/tjstats/v1/scout-pitchers",
        primary_columns=(
            "player_id", "fv", "fastball_pv", "fastball_fv",
            "slider_pv", "slider_fv", "curveball_pv", "curveball_fv",
            "changeup_pv", "changeup_fv", "splitter_pv", "splitter_fv",
            "command_pv", "command_fv", "eta", "risk",
        ),
        target_table="tjstats_scout_pitchers",
        ingested=True,
        notes=(
            "Per-pitcher 20-80 grades on individual pitch types (present + future "
            "value). Richer than FanGraphs aggregate FV — gives the dev-fit feature "
            "space a per-pitch decomposition. Current snapshot only."
        ),
    ),
    StatSource(
        name="tjstats-scout-batters",
        source="tjstats",
        granularity="player-career",
        era_start=2026,
        era_end=None,
        fetcher="tjstats.ca/wp-json/tjstats/v1/scout-batters",
        primary_columns=(
            "player_id", "fv", "hit_pv", "hit_fv", "power_pv", "power_fv",
            "decisions_pv", "decisions_fv", "speed_pv", "speed_fv",
            "defense_pv", "defense_fv", "eta",
        ),
        target_table="tjstats_scout_batters",
        ingested=True,
        notes=(
            "Per-hitter 20-80 grades: hit / power / decisions / speed / defense, "
            "present + future. Current snapshot only."
        ),
    ),
    StatSource(
        name="tjstats-draft-rankings",
        source="tjstats",
        granularity="draft",
        era_start=2026,
        era_end=None,
        fetcher="tjstats.ca/wp-json/tjstats/v1/draft-rankings",
        primary_columns=("player_id", "rank_value", "name", "position", "team"),
        target_table=None,
        ingested=False,
        notes="TJStats' own draft prospect rankings. Current cycle only.",
    ),
    StatSource(
        name="tjstats-tjbat",
        source="tjstats",
        granularity="player-season",
        era_start=2024,
        era_end=None,
        fetcher="tjstats.ca/wp-json/tjstats/v1/tjbat?player_id=X",
        primary_columns=(
            "player_id", "season", "level", "pa",
            "woba_plus", "tjbat_plus", "tjbat_plus_pctile", "woba_plus_pctile",
        ),
        target_table=None,
        ingested=False,
        notes=(
            "tjbat+ regression-baseline hitting metric per (player, season, level), "
            "covers MiLB levels (lo-a/hi-a/aa/aaa). Useful for minor-league "
            "offensive evaluation where Statcast coverage is limited."
        ),
    ),
    # === MLB Pipeline (mlb.com/prospects, public; current snapshot) ===
    StatSource(
        name="mlb-pipeline-prospects",
        source="mlb-pipeline",
        granularity="player-season",
        era_start=2026,
        era_end=None,
        fetcher="savage_trade_evaluator.ingest.mlb_pipeline.ingest",
        primary_columns=(
            "mlbam_id", "rank", "overall_grade", "eta",
            "hit", "power", "run", "arm", "field",
            "fastball", "slider", "curveball", "changeup", "control",
        ),
        target_table="mlb_pipeline_prospects",
        ingested=True,
        notes=(
            "MLB Pipeline current top-100 with 20-80 scouting grades. Plain httpx "
            "(no Cloudflare/Firecrawl): rankings page embeds a 'data' JS global; "
            "per-player /scouting-report endpoint carries tool grades + Overall "
            "(FV-equivalent) + ETA in prose. player_id is MLBAM (no bridging). "
            "Third independent current FV source alongside FG Board + TJStats. "
            "Current snapshot only — page is current-only; keyed (fetched_at, "
            "mlbam_id). Historical pre-2017 prospect rankings remain a known gap "
            "(no clean free source; FG Board covers 2017+)."
        ),
    ),
)


# === Helpers ===


def by_source(source: Source) -> list[StatSource]:
    """Return all catalog entries from one upstream provider."""
    return [s for s in CATALOG if s.source == source]


def by_granularity(g: Granularity) -> list[StatSource]:
    """Return all entries at a particular row granularity."""
    return [s for s in CATALOG if s.granularity == g]


def ingested() -> list[StatSource]:
    """Return only the sources we currently have a working adapter for."""
    return [s for s in CATALOG if s.ingested]


def available_not_yet_ingested() -> list[StatSource]:
    """Sources we know how to fetch but haven't wired up."""
    return [s for s in CATALOG if not s.ingested and not s.blocked]


def blocked() -> list[StatSource]:
    """Sources we know about but can't currently access."""
    return [s for s in CATALOG if s.blocked]


def covers_year(year: int) -> list[StatSource]:
    """All sources that have data for a given calendar year."""
    return [s for s in CATALOG if s.era_start <= year and (s.era_end is None or year <= s.era_end)]


def search(term: str) -> list[StatSource]:
    """Substring search across name, notes, and primary_columns."""
    needle = term.lower()
    out: list[StatSource] = []
    for s in CATALOG:
        haystack = " ".join((s.name, s.notes, *s.primary_columns)).lower()
        if needle in haystack:
            out.append(s)
    return out
