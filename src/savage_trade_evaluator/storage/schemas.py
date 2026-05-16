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


SCHEMA_VERSION = 3

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
