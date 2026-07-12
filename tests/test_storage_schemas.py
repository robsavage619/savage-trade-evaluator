"""Hermetic tests for storage/schemas.py against an in-memory DuckDB."""

from __future__ import annotations

import duckdb

from savage_trade_evaluator.storage import outcome_views, teams, trade_views
from savage_trade_evaluator.storage.schemas import SCHEMA_VERSION, initialize


def _table_names(conn: duckdb.DuckDBPyConnection) -> set[str]:
    rows = conn.execute("SELECT table_name FROM information_schema.tables").fetchall()
    return {r[0] for r in rows}


def test_schema_version_is_35() -> None:
    assert SCHEMA_VERSION == 35


def test_initialize_records_schema_version() -> None:
    conn = duckdb.connect(":memory:")
    initialize(conn)
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    assert [r[0] for r in rows] == [SCHEMA_VERSION]


def test_initialize_is_idempotent() -> None:
    conn = duckdb.connect(":memory:")
    initialize(conn)
    initialize(conn)
    (n,) = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone() or (None,)
    assert n == 1


def test_initialize_creates_core_tables() -> None:
    conn = duckdb.connect(":memory:")
    initialize(conn)
    tables = _table_names(conn)
    expected = {
        "transactions",
        "bwar_batting",
        "bwar_pitching",
        "prospect_rankings",
        "prospect_fv_calibration",
        "gm_behavioral_profiles",
        "gm_archetypes",
        "war_room_briefs",
        "spotrac_team_payroll",
    }
    assert expected <= tables


def test_migration_recreates_prospect_rankings_with_fv() -> None:
    conn = duckdb.connect(":memory:")
    conn.execute(
        "CREATE TABLE prospect_rankings (rank_year INTEGER, rank INTEGER, player_name VARCHAR)"
    )
    initialize(conn)
    cols = {
        r[0]
        for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'prospect_rankings'"
        ).fetchall()
    }
    assert "fv" in cols
    assert "player_name_norm" in cols


def test_full_init_flow_on_fresh_db() -> None:
    """The real ``ste init`` order: schemas, then teams, then views.

    Regression guard for a DDL-ordering bug where trade_acquired_prospect_fv
    (once defined inside schemas.DDL_STATEMENTS) referenced trade_player_unified
    and chadwick_register before either existed on a truly fresh database.
    """
    conn = duckdb.connect(":memory:")
    initialize(conn)
    teams.initialize(conn)
    trade_views.create_all(conn)
    outcome_views.create_all(conn)
    assert "trade_acquired_prospect_fv" in _table_names(conn)
