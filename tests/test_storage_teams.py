"""Hermetic tests for the MLB-id / Baseball-Reference team-code bridge."""

from __future__ import annotations

import duckdb

from savage_trade_evaluator.storage import teams


def _initialized_conn() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    teams.initialize(conn)
    return conn


def test_teams_constant_has_30_unique_franchises() -> None:
    assert len(teams.TEAMS) == 30
    assert len({t[0] for t in teams.TEAMS}) == 30
    assert len({t[2] for t in teams.TEAMS}) == 30


def test_initialize_loads_all_teams_and_aliases() -> None:
    conn = _initialized_conn()
    (n_teams,) = conn.execute("SELECT COUNT(*) FROM teams").fetchone() or (None,)
    (n_aliases,) = conn.execute("SELECT COUNT(*) FROM team_aliases").fetchone() or (None,)
    assert n_teams == 30
    assert n_aliases == len(teams.HISTORICAL_BREF_ALIASES)


def test_initialize_is_idempotent() -> None:
    conn = _initialized_conn()
    teams.initialize(conn)
    (n_teams,) = conn.execute("SELECT COUNT(*) FROM teams").fetchone() or (None,)
    assert n_teams == 30


def test_divergent_mlb_to_bref_mappings() -> None:
    conn = _initialized_conn()
    rows = conn.execute("SELECT mlb_abbrev, bref_code FROM teams").fetchall()
    mapping = dict(rows)
    assert mapping["KC"] == "KCR"
    assert mapping["SF"] == "SFG"
    assert mapping["TB"] == "TBR"
    assert mapping["WSH"] == "WSN"
    assert mapping["CWS"] == "CHW"
    assert mapping["SD"] == "SDP"
    assert mapping["AZ"] == "ARI"
    assert mapping["ATH"] == "OAK"


def test_historical_aliases_resolve_to_current_franchises() -> None:
    conn = _initialized_conn()
    rows = conn.execute(
        "SELECT a.bref_code, t.name FROM team_aliases a "
        "JOIN teams t ON t.mlb_team_id = a.mlb_team_id"
    ).fetchall()
    resolved = dict(rows)
    assert resolved["FLA"] == "Miami Marlins"
    assert resolved["MON"] == "Washington Nationals"
    assert resolved["TBD"] == "Tampa Bay Rays"
    assert resolved["ANA"] == "Los Angeles Angels"
