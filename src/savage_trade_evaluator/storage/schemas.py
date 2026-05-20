"""Versioned DDL for the trade-eval DuckDB schemas.

Schemas evolve via additive migrations. Each table carries an ``ingested_at``
column for provenance and a ``source`` column naming the upstream system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)


SCHEMA_VERSION = 23

DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER NOT NULL,
        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id BIGINT NOT NULL,
        leg_index INTEGER NOT NULL,
        date DATE NOT NULL,
        effective_date DATE,
        resolution_date DATE,
        type_code VARCHAR NOT NULL,
        type_desc VARCHAR,
        description VARCHAR,
        from_team_id INTEGER,
        from_team_name VARCHAR,
        to_team_id INTEGER,
        to_team_name VARCHAR,
        player_id INTEGER,
        player_name VARCHAR,
        season INTEGER NOT NULL,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (transaction_id, leg_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_season ON transactions(season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type_code)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_transactions_trade_event
        ON transactions(transaction_id, type_code)
    """,
    """
    CREATE TABLE IF NOT EXISTS bwar_batting (
        mlb_id INTEGER,
        bref_id VARCHAR NOT NULL,
        name_common VARCHAR,
        year_id INTEGER NOT NULL,
        team_id VARCHAR,
        stint_id INTEGER NOT NULL,
        lg_id VARCHAR,
        is_pitcher BOOLEAN,
        g INTEGER,
        pa INTEGER,
        salary DOUBLE,
        runs_above_avg DOUBLE,
        runs_above_avg_off DOUBLE,
        runs_above_avg_def DOUBLE,
        war_rep DOUBLE,
        waa DOUBLE,
        war DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (bref_id, year_id, stint_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bwar_batting_year ON bwar_batting(year_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bwar_batting_mlb ON bwar_batting(mlb_id, year_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS bwar_pitching (
        mlb_id INTEGER,
        bref_id VARCHAR NOT NULL,
        name_common VARCHAR,
        year_id INTEGER NOT NULL,
        team_id VARCHAR,
        stint_id INTEGER NOT NULL,
        lg_id VARCHAR,
        g INTEGER,
        gs INTEGER,
        ra INTEGER,
        xra DOUBLE,
        bip DOUBLE,
        bip_perc DOUBLE,
        salary DOUBLE,
        era_plus DOUBLE,
        war_rep DOUBLE,
        waa DOUBLE,
        waa_adj DOUBLE,
        war DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (bref_id, year_id, stint_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bwar_pitching_year ON bwar_pitching(year_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bwar_pitching_mlb ON bwar_pitching(mlb_id, year_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_batting_expected (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        year INTEGER NOT NULL,
        pa INTEGER,
        bip INTEGER,
        ba DOUBLE,
        est_ba DOUBLE,
        slg DOUBLE,
        est_slg DOUBLE,
        woba DOUBLE,
        est_woba DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_pitching_expected (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        year INTEGER NOT NULL,
        pa INTEGER,
        bip INTEGER,
        ba DOUBLE,
        est_ba DOUBLE,
        slg DOUBLE,
        est_slg DOUBLE,
        woba DOUBLE,
        est_woba DOUBLE,
        era DOUBLE,
        xera DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_pitcher_percentile_ranks (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        year INTEGER NOT NULL,
        xwoba DOUBLE,
        xba DOUBLE,
        xslg DOUBLE,
        xiso DOUBLE,
        xobp DOUBLE,
        brl DOUBLE,
        brl_percent DOUBLE,
        exit_velocity DOUBLE,
        max_ev DOUBLE,
        hard_hit_percent DOUBLE,
        k_percent DOUBLE,
        bb_percent DOUBLE,
        whiff_percent DOUBLE,
        chase_percent DOUBLE,
        arm_strength DOUBLE,
        xera DOUBLE,
        fb_velocity DOUBLE,
        fb_spin DOUBLE,
        curve_spin DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_statcast_bat_year ON statcast_batting_expected(year)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_statcast_pit_year ON statcast_pitching_expected(year)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_statcast_pct_year ON statcast_pitcher_percentile_ranks(year)
    """,
    """
    CREATE TABLE IF NOT EXISTS coaches (
        team_id INTEGER NOT NULL,
        season INTEGER NOT NULL,
        job_code VARCHAR NOT NULL,
        job_title VARCHAR,
        person_id INTEGER,
        person_name VARCHAR,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_id, season, job_code, person_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_coaches_team_season ON coaches(team_id, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_coaches_job ON coaches(job_code, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS front_office (
        team_id INTEGER NOT NULL,
        bref_code VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        role VARCHAR NOT NULL,
        person_name VARCHAR NOT NULL,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_id, season, role, person_name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_front_office_team_season ON front_office(team_id, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_front_office_role ON front_office(role, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS naive_baseline_results (
        trade_event_id BIGINT NOT NULL,
        trade_season INTEGER NOT NULL,
        outcome_window_years INTEGER NOT NULL,
        team_bref VARCHAR NOT NULL,
        war_received DOUBLE NOT NULL,
        war_given_up DOUBLE NOT NULL,
        surplus DOUBLE NOT NULL,
        players_received VARCHAR,
        players_given_up VARCHAR,
        evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (trade_event_id, team_bref, outcome_window_years)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_nbr_season ON naive_baseline_results(trade_season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_nbr_surplus ON naive_baseline_results(surplus)
    """,
    """
    CREATE TABLE IF NOT EXISTS team_season_features (
        team_id INTEGER NOT NULL,
        bref_code VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        prior_year_wins INTEGER,
        prior_year_losses INTEGER,
        prior_year_run_diff INTEGER,
        prior_year_pyth_pct DOUBLE,
        prior_year_war DOUBLE,
        farm_war_top_10 DOUBLE,
        org_dev_fit_pitching DOUBLE,
        org_dev_fit_hitting DOUBLE,
        org_pitcher_k_jump_3yr DOUBLE,
        org_hitter_xwoba_jump_3yr DOUBLE,
        coach_hitter_xwoba_jump_3yr DOUBLE,
        tech_adoption_lead_years REAL,
        alumni_network_score DOUBLE,
        origin_sunk_cost_pressure DOUBLE,
        org_pitcher_k_jump_recency_bias DOUBLE,
        computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_id, season)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tsf_season ON team_season_features(season)
    """,
    """
    CREATE TABLE IF NOT EXISTS standings (
        team_id INTEGER NOT NULL,
        bref_code VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        wins INTEGER NOT NULL,
        losses INTEGER NOT NULL,
        win_pct DOUBLE NOT NULL,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_id, season)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_standings_season ON standings(season)
    """,
    """
    CREATE TABLE IF NOT EXISTS prospect_rankings (
        rank_year INTEGER NOT NULL,
        rank INTEGER NOT NULL,
        mlb_player_id INTEGER NOT NULL,
        player_name VARCHAR NOT NULL,
        position VARCHAR,
        team_id INTEGER,
        team_name VARCHAR,
        level VARCHAR,
        age INTEGER,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (rank_year, mlb_player_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prospects_player ON prospect_rankings(mlb_player_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prospects_year ON prospect_rankings(rank_year)
    """,
    """
    CREATE TABLE IF NOT EXISTS draft_picks (
        draft_year INTEGER NOT NULL,
        pick_number INTEGER NOT NULL,
        pick_round VARCHAR,
        round_pick_number INTEGER,
        overall_rank INTEGER,
        pick_value DOUBLE,
        signing_bonus DOUBLE,
        is_drafted BOOLEAN,
        is_pass BOOLEAN,
        mlb_player_id INTEGER,
        player_name VARCHAR,
        team_id INTEGER,
        team_name VARCHAR,
        school_name VARCHAR,
        scouting_report VARCHAR,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (draft_year, pick_number)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_draft_player ON draft_picks(mlb_player_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_draft_year ON draft_picks(draft_year)
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_batter_percentile_ranks (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        year INTEGER NOT NULL,
        xwoba DOUBLE,
        xba DOUBLE,
        xslg DOUBLE,
        xiso DOUBLE,
        xobp DOUBLE,
        brl DOUBLE,
        brl_percent DOUBLE,
        exit_velocity DOUBLE,
        max_ev DOUBLE,
        hard_hit_percent DOUBLE,
        k_percent DOUBLE,
        bb_percent DOUBLE,
        whiff_percent DOUBLE,
        chase_percent DOUBLE,
        arm_strength DOUBLE,
        sprint_speed DOUBLE,
        oaa DOUBLE,
        bat_speed DOUBLE,
        squared_up_rate DOUBLE,
        swing_length DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_batter_pct_year ON statcast_batter_percentile_ranks(year)
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_pitcher_arsenal_stats (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        team_name VARCHAR,
        year INTEGER NOT NULL,
        pitch_type VARCHAR NOT NULL,
        pitch_name VARCHAR,
        run_value_per_100 DOUBLE,
        run_value DOUBLE,
        pitches INTEGER,
        pitch_usage DOUBLE,
        pa INTEGER,
        ba DOUBLE,
        slg DOUBLE,
        woba DOUBLE,
        whiff_percent DOUBLE,
        k_percent DOUBLE,
        put_away DOUBLE,
        est_ba DOUBLE,
        est_slg DOUBLE,
        est_woba DOUBLE,
        hard_hit_percent DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year, pitch_type)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pitcher_arsenal_player_year
        ON statcast_pitcher_arsenal_stats(player_id, year)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pitcher_arsenal_year
        ON statcast_pitcher_arsenal_stats(year)
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_outs_above_average (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        team_name VARCHAR,
        year INTEGER NOT NULL,
        primary_pos VARCHAR NOT NULL,
        fielding_runs_prevented DOUBLE,
        oaa DOUBLE,
        oaa_infront DOUBLE,
        oaa_lateral_toward3b DOUBLE,
        oaa_lateral_toward1b DOUBLE,
        oaa_behind DOUBLE,
        oaa_rhh DOUBLE,
        oaa_lhh DOUBLE,
        actual_success_rate DOUBLE,
        adj_estimated_success_rate DOUBLE,
        diff_success_rate DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year, primary_pos)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_oaa_player_year
        ON statcast_outs_above_average(player_id, year)
    """,
    """
    CREATE TABLE IF NOT EXISTS chadwick_register (
        mlb_player_id INTEGER NOT NULL,
        retro_id VARCHAR,
        bref_id VARCHAR,
        fangraphs_id VARCHAR,
        name_first VARCHAR,
        name_last VARCHAR,
        name_given VARCHAR,
        birth_year INTEGER,
        birth_month INTEGER,
        birth_day INTEGER,
        death_year INTEGER,
        death_month INTEGER,
        death_day INTEGER,
        pro_played_first INTEGER,
        pro_played_last INTEGER,
        mlb_played_first INTEGER,
        mlb_played_last INTEGER,
        col_played_first INTEGER,
        col_played_last INTEGER,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (mlb_player_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chadwick_bref ON chadwick_register(bref_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chadwick_retro ON chadwick_register(retro_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_catcher_framing (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        year INTEGER NOT NULL,
        pitches INTEGER,
        runs_total DOUBLE,
        strike_rate_total DOUBLE,
        rv_11 DOUBLE,
        pct_11 DOUBLE,
        rv_12 DOUBLE,
        pct_12 DOUBLE,
        rv_13 DOUBLE,
        pct_13 DOUBLE,
        rv_14 DOUBLE,
        pct_14 DOUBLE,
        rv_16 DOUBLE,
        pct_16 DOUBLE,
        rv_17 DOUBLE,
        pct_17 DOUBLE,
        rv_18 DOUBLE,
        pct_18 DOUBLE,
        rv_19 DOUBLE,
        pct_19 DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_catcher_framing_year ON statcast_catcher_framing(year)
    """,
    """
    CREATE TABLE IF NOT EXISTS mlb_awards (
        award_id VARCHAR NOT NULL,
        award_name VARCHAR,
        season INTEGER NOT NULL,
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        team_id INTEGER,
        team_name VARCHAR,
        votes DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (award_id, season, player_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_awards_player ON mlb_awards(player_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_awards_season ON mlb_awards(season)
    """,
    """
    CREATE TABLE IF NOT EXISTS game_logs (
        game_date DATE NOT NULL,
        game_number VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        day_of_week VARCHAR,
        visitor_team_bref VARCHAR NOT NULL,
        visitor_league VARCHAR,
        visitor_game_number INTEGER,
        home_team_bref VARCHAR NOT NULL,
        home_league VARCHAR,
        home_game_number INTEGER,
        visitor_score INTEGER,
        home_score INTEGER,
        game_length_outs INTEGER,
        day_night VARCHAR,
        park_id VARCHAR,
        attendance INTEGER,
        game_time_minutes INTEGER,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (game_date, game_number, home_team_bref, visitor_team_bref)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_game_logs_season ON game_logs(season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_game_logs_home ON game_logs(home_team_bref, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_game_logs_visitor ON game_logs(visitor_team_bref, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS mlb_people (
        mlb_player_id INTEGER NOT NULL,
        full_name VARCHAR,
        birth_date DATE,
        birth_city VARCHAR,
        birth_state_province VARCHAR,
        birth_country VARCHAR,
        height_inches INTEGER,
        weight_lbs INTEGER,
        bat_side VARCHAR,
        pitch_hand VARCHAR,
        primary_position_code VARCHAR,
        primary_position_name VARCHAR,
        primary_position_type VARCHAR,
        mlb_debut_date DATE,
        last_played_date DATE,
        active BOOLEAN,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (mlb_player_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_people_country ON mlb_people(birth_country)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_people_position ON mlb_people(primary_position_code)
    """,
    """
    CREATE TABLE IF NOT EXISTS retrosheet_parks (
        park_id VARCHAR NOT NULL,
        name VARCHAR,
        aka VARCHAR,
        city VARCHAR,
        state VARCHAR,
        start_date VARCHAR,
        end_date VARCHAR,
        league VARCHAR,
        notes VARCHAR,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (park_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS statcast_pitch_movement (
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        team_abbrev VARCHAR,
        year INTEGER NOT NULL,
        pitch_hand VARCHAR,
        pitch_type VARCHAR NOT NULL,
        pitch_name VARCHAR,
        avg_speed DOUBLE,
        pitches_thrown INTEGER,
        pitch_usage_pct DOUBLE,
        vertical_break_inches DOUBLE,
        league_vertical_break DOUBLE,
        diff_vertical DOUBLE,
        induced_vertical DOUBLE,
        horizontal_break_inches DOUBLE,
        league_horizontal_break DOUBLE,
        diff_horizontal DOUBLE,
        percentile_diff_vertical DOUBLE,
        percentile_diff_horizontal DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (player_id, year, pitch_type)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pitch_movement_year ON statcast_pitch_movement(year)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_pitch_movement_player_year
        ON statcast_pitch_movement(player_id, year)
    """,
    """
    CREATE TABLE IF NOT EXISTS team_rosters (
        team_id INTEGER NOT NULL,
        team_bref VARCHAR,
        season INTEGER NOT NULL,
        roster_type VARCHAR NOT NULL,
        player_id INTEGER NOT NULL,
        player_name VARCHAR,
        position_code VARCHAR,
        position_name VARCHAR,
        status VARCHAR,
        jersey_number VARCHAR,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_id, season, roster_type, player_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rosters_player ON team_rosters(player_id, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rosters_team_season ON team_rosters(team_id, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS mlb_venues (
        venue_id INTEGER NOT NULL,
        name VARCHAR,
        city VARCHAR,
        state_abbrev VARCHAR,
        country VARCHAR,
        capacity INTEGER,
        turf_type VARCHAR,
        roof_type VARCHAR,
        left_field_ft INTEGER,
        left_center_ft INTEGER,
        center_field_ft INTEGER,
        right_center_ft INTEGER,
        right_field_ft INTEGER,
        active BOOLEAN,
        season VARCHAR,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (venue_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_venues_active ON mlb_venues(active)
    """,
    """
    CREATE TABLE IF NOT EXISTS team_season_stats (
        team_id INTEGER NOT NULL,
        team_bref VARCHAR,
        season INTEGER NOT NULL,
        stat_group VARCHAR NOT NULL,
        games_played INTEGER,
        runs INTEGER,
        hits INTEGER,
        doubles INTEGER,
        triples INTEGER,
        home_runs INTEGER,
        strike_outs INTEGER,
        base_on_balls INTEGER,
        avg DOUBLE,
        obp DOUBLE,
        slg DOUBLE,
        ops DOUBLE,
        era DOUBLE,
        whip DOUBLE,
        innings_pitched DOUBLE,
        earned_runs INTEGER,
        stolen_bases INTEGER,
        caught_stealing INTEGER,
        fielding_pct DOUBLE,
        errors INTEGER,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_id, season, stat_group)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tss_season ON team_season_stats(season, stat_group)
    """,
    """
    CREATE TABLE IF NOT EXISTS spotrac_player_contracts (
        spotrac_id INTEGER NOT NULL,
        mlb_player_id INTEGER,
        player_name VARCHAR NOT NULL,
        team_bref VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        position VARCHAR,
        service_time DOUBLE,
        acquired_method VARCHAR,
        status VARCHAR,
        base_salary BIGINT,
        cap_hit BIGINT,
        signing_bonus BIGINT,
        incentives BIGINT,
        table_type VARCHAR NOT NULL,
        spotrac_slug VARCHAR,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (spotrac_id, season, table_type)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_spotrac_player_year
        ON spotrac_player_contracts(mlb_player_id, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_spotrac_team_season
        ON spotrac_player_contracts(team_bref, season)
    """,
    """
    CREATE TABLE IF NOT EXISTS spotrac_team_payroll (
        team_bref VARCHAR NOT NULL,
        team_slug VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        active_players INTEGER,
        active_payroll BIGINT,
        dead_money BIGINT,
        injured_payroll BIGINT,
        total_payroll BIGINT,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (team_bref, season)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_spotrac_team_payroll_season
        ON spotrac_team_payroll(season)
    """,
    """
    -- MiLB seasonal stats from MLB Stats API sportId={11,12,13,14}.
    -- One row per (player, season, sport_id, team_id, group) tuple — same
    -- player can appear at multiple levels in one season (promotions /
    -- demotions). 'group' is 'hitting' or 'pitching'.
    CREATE TABLE IF NOT EXISTS milb_player_seasons (
        mlb_player_id INTEGER NOT NULL,
        season INTEGER NOT NULL,
        sport_id INTEGER NOT NULL,
        team_id INTEGER NOT NULL,
        group_name VARCHAR NOT NULL,
        player_name VARCHAR,
        team_name VARCHAR,
        league_id INTEGER,
        position VARCHAR,
        age INTEGER,
        games_played INTEGER,
        plate_appearances INTEGER,
        at_bats INTEGER,
        runs INTEGER,
        hits INTEGER,
        doubles INTEGER,
        triples INTEGER,
        home_runs INTEGER,
        rbi INTEGER,
        stolen_bases INTEGER,
        strikeouts INTEGER,
        walks INTEGER,
        hbp INTEGER,
        avg DOUBLE,
        obp DOUBLE,
        slg DOUBLE,
        ops DOUBLE,
        babip DOUBLE,
        innings_pitched DOUBLE,
        era DOUBLE,
        wins INTEGER,
        losses INTEGER,
        saves INTEGER,
        games_started INTEGER,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (mlb_player_id, season, sport_id, team_id, group_name)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_milb_player_seasons_season
        ON milb_player_seasons(season, sport_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_milb_player_seasons_player
        ON milb_player_seasons(mlb_player_id, season)
    """,
    # --- Retrosheet event-log derived tables (adapter in ingest/retrosheet_events.py) ---
    """
    CREATE TABLE IF NOT EXISTS retrosheet_game_appearances (
        team VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        game_id VARCHAR NOT NULL,
        pitcher_id VARCHAR NOT NULL,
        is_reliever BOOLEAN NOT NULL,
        n_batters_faced INTEGER NOT NULL,
        avg_li DOUBLE,
        leverage_ge_1_5_pct DOUBLE,
        leverage_lt_0_7_pct DOUBLE,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (game_id, pitcher_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rga_team_season
        ON retrosheet_game_appearances(team, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rga_reliever
        ON retrosheet_game_appearances(season, is_reliever)
    """,
    """
    CREATE TABLE IF NOT EXISTS retrosheet_pa_matchups (
        team VARCHAR NOT NULL,
        season INTEGER NOT NULL,
        game_id VARCHAR NOT NULL,
        bat_hand VARCHAR NOT NULL,
        pit_hand VARCHAR NOT NULL,
        event_cd INTEGER NOT NULL,
        runs_scored INTEGER NOT NULL,
        source VARCHAR NOT NULL,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rpm_team_season
        ON retrosheet_pa_matchups(team, season)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_rpm_matchup
        ON retrosheet_pa_matchups(season, bat_hand, pit_hand)
    """,
)


def initialize(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply all DDL idempotently and record the schema version.

    Args:
        conn: An open DuckDB connection.
    """
    for stmt in DDL_STATEMENTS:
        conn.execute(stmt)

    current = conn.execute("SELECT max(version) FROM schema_version").fetchone()
    if current is None or current[0] != SCHEMA_VERSION:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", [SCHEMA_VERSION])
        logger.info("schema initialized at version %d", SCHEMA_VERSION)
