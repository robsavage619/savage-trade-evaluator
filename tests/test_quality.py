from __future__ import annotations

from datetime import datetime, timedelta

import duckdb

from savage_trade_evaluator import quality as q

NOW = datetime(2026, 11, 13, 5, 30)
TODAY = NOW.date()
STALE = NOW - timedelta(days=100)


def _db(
    *, frozen: set[str] | None = None, clubs: int = 30, spotrac_stale: bool = False
) -> duckdb.DuckDBPyConnection:
    """A database that looks like a good refresh; knobs break one thing at a time."""
    frozen = frozen or set()
    conn = duckdb.connect()
    for t in q.CURRENT_TABLES:
        stale = t.name in frozen or (spotrac_stale and t.name.startswith("spotrac"))
        conn.execute(
            f"CREATE TABLE {t.name} ({t.season_col} INTEGER, ingested_at TIMESTAMP, "
            "war DOUBLE, g INTEGER, wins INTEGER, losses INTEGER)"
        )
        for _ in range(100):
            conn.execute(
                f"INSERT INTO {t.name} VALUES (2026, ?, ?, ?, ?, ?)",
                [STALE if stale else NOW, 1.0, 162, 80, 60],
            )
    conn.execute("DELETE FROM standings")
    for _ in range(clubs):
        conn.execute("INSERT INTO standings VALUES (2026, ?, 1.0, 100, 90, 72)", [NOW])
    conn.execute(
        "CREATE TABLE team_rosters (team_bref VARCHAR, season INTEGER, ingested_at TIMESTAMP)"
    )
    for club in range(30):
        for _ in range(33):
            conn.execute("INSERT INTO team_rosters VALUES (?, 2026, ?)", [f"T{club}", NOW])
    conn.execute("CREATE TABLE transactions (date DATE)")
    conn.execute("INSERT INTO transactions VALUES (?)", [TODAY - timedelta(days=1)])
    conn.execute("CREATE TABLE bref_contract_players (as_of DATE)")
    conn.execute("CREATE TABLE fg_projections (as_of DATE)")
    for _ in range(1100):
        conn.execute("INSERT INTO bref_contract_players VALUES (?)", [TODAY])
    for _ in range(4100):
        conn.execute("INSERT INTO fg_projections VALUES (?)", [TODAY])
    return conn


def _run(conn: duckdb.DuckDBPyConnection, baseline: dict | None = None) -> tuple[str, list[q.Gate]]:
    gates, _ = q.run_gates(
        conn, season=2026, since=NOW - timedelta(hours=1), today=TODAY, baseline=baseline
    )
    return q.overall(gates), gates


def _failed(gates: list[q.Gate]) -> set[str]:
    return {g.name for g in gates if not g.ok}


def test_a_good_refresh_passes_every_gate() -> None:
    status, gates = _run(_db())
    assert status == "ok", _failed(gates)


def test_a_frozen_table_blocks_publishing() -> None:
    status, gates = _run(_db(frozen={"bwar_batting"}))
    assert status == "failed" and "fresh:bwar_batting" in _failed(gates)


def test_a_lagging_spotrac_only_degrades() -> None:
    status, gates = _run(_db(spotrac_stale=True))
    assert status == "degraded"
    assert _failed(gates) == {
        "fresh:spotrac_player_contracts",
        "fresh:spotrac_team_payroll",
        "fresh:spotrac_contract_terms",
    }


def test_a_club_missing_from_standings_blocks_publishing() -> None:
    status, gates = _run(_db(clubs=29))
    assert status == "failed" and "standings:30 clubs" in _failed(gates)


def test_shrinking_tables_and_falling_war_are_caught_against_the_last_good_run() -> None:
    conn = _db()
    metrics = q.collect_metrics(conn, 2026)
    assert _run(conn, baseline=metrics)[0] == "ok"
    worse = {
        **metrics,
        "rows:bwar_batting": 1000,
        "bwar_batting_war": 5000.0,
        "standings_wins": 99999,
    }
    status, gates = _run(conn, baseline=worse)
    assert status == "failed"
    assert {"no-shrink:bwar_batting", "bwar:war-only-grows", "standings:wins-only-grow"} <= _failed(
        gates
    )


def test_a_new_season_or_first_run_is_not_compared_to_nothing() -> None:
    conn = _db()
    assert _run(conn, baseline=None)[0] == "ok"
    assert _run(conn, baseline={"season": 2025, "bwar_batting_war": 1e9})[0] == "ok"
