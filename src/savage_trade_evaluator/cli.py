"""Typer-based CLI: ``ste ingest transactions --season 2018`` etc."""

from __future__ import annotations

import logging

import typer

from savage_trade_evaluator.config import (
    BACKTESTER_END_SEASON,
    BACKTESTER_START_SEASON,
    configure_logging,
)
from savage_trade_evaluator.ingest import stats, transactions
from savage_trade_evaluator.storage import db, schemas, trade_views

app = typer.Typer(no_args_is_help=True, help="Savage Trade Evaluator CLI.")
ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion commands.")
app.add_typer(ingest_app, name="ingest")

logger = logging.getLogger(__name__)


@app.command()
def init() -> None:
    """Initialize the DuckDB schema and trade-event views."""
    configure_logging()
    with db.connect() as conn:
        schemas.initialize(conn)
        trade_views.create_all(conn)
    typer.echo("schema initialized")


@ingest_app.command("transactions")
def ingest_transactions(
    season: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(BACKTESTER_START_SEASON, help="First season (inclusive)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season (inclusive)."),
) -> None:
    """Pull MLB transactions from the Stats API and store them in DuckDB.

    Use ``--season YYYY`` for one year, or ``--start YYYY --end YYYY`` for a range.
    """
    configure_logging()
    seasons = [season] if season else list(range(start, end + 1))
    total = 0
    for s in seasons:
        total += transactions.ingest_season(s)
    typer.echo(f"ingested {total} transactions across {len(seasons)} season(s)")


@ingest_app.command("bwar")
def ingest_bwar() -> None:
    """Pull bWAR batting + pitching tables (1871-present) from Baseball Reference."""
    configure_logging()
    batting = stats.ingest_bwar_batting()
    pitching = stats.ingest_bwar_pitching()
    typer.echo(f"ingested bWAR: {batting} batting rows + {pitching} pitching rows")


@ingest_app.command("statcast")
def ingest_statcast(
    season: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(2015, help="First season (Statcast era starts 2015)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season (inclusive)."),
    skip_percentiles: bool = typer.Option(
        False, help="Skip pitcher percentile ranks (arsenal data)."
    ),
) -> None:
    """Pull Baseball Savant Statcast expected stats + pitcher percentile ranks."""
    configure_logging()
    seasons = [season] if season else list(range(start, end + 1))
    bat_total = 0
    pit_total = 0
    pct_total = 0
    for s in seasons:
        bat_total += stats.ingest_statcast_batting_expected(s)
        pit_total += stats.ingest_statcast_pitching_expected(s)
        if not skip_percentiles:
            pct_total += stats.ingest_statcast_pitcher_percentile_ranks(s)
    typer.echo(
        f"ingested Statcast: {bat_total} bat-expected, "
        f"{pit_total} pit-expected, {pct_total} percentile-ranks "
        f"across {len(seasons)} season(s)"
    )


@app.command()
def status() -> None:
    """Print a summary of what's in the DuckDB store."""
    configure_logging()
    with db.connect(read_only=True) as conn:
        count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()
        if count is None:
            typer.echo("no transactions table")
            return
        seasons = conn.execute(
            "SELECT season, COUNT(*) FROM transactions GROUP BY season ORDER BY season"
        ).fetchall()
        trade_events = conn.execute("SELECT COUNT(*) FROM trade_events").fetchone()
        affiliated = conn.execute("SELECT COUNT(*) FROM trade_events_affiliated").fetchone()
    with db.connect(read_only=True) as conn:
        bwar_bat = conn.execute("SELECT COUNT(*) FROM bwar_batting").fetchone()
        bwar_pit = conn.execute("SELECT COUNT(*) FROM bwar_pitching").fetchone()
        statcast_bat = conn.execute("SELECT COUNT(*) FROM statcast_batting_expected").fetchone()
        statcast_pit = conn.execute("SELECT COUNT(*) FROM statcast_pitching_expected").fetchone()
        statcast_pct = conn.execute(
            "SELECT COUNT(*) FROM statcast_pitcher_percentile_ranks"
        ).fetchone()

    typer.echo(f"total transactions:                {count[0]}")
    typer.echo(f"trade events (all):                {trade_events[0] if trade_events else 0}")
    typer.echo(f"trade events (MLB-only):           {affiliated[0] if affiliated else 0}")
    typer.echo(f"bwar batting rows:                 {bwar_bat[0] if bwar_bat else 0}")
    typer.echo(f"bwar pitching rows:                {bwar_pit[0] if bwar_pit else 0}")
    typer.echo(f"statcast batting expected:         {statcast_bat[0] if statcast_bat else 0}")
    typer.echo(f"statcast pitching expected:        {statcast_pit[0] if statcast_pit else 0}")
    typer.echo(f"statcast pitcher percentile ranks: {statcast_pct[0] if statcast_pct else 0}")
    typer.echo("per-season transactions:")
    for s, n in seasons:
        typer.echo(f"  {s}: {n}")
