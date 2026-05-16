"""Typer-based CLI: ``ste ingest transactions --season 2018`` etc."""

from __future__ import annotations

import logging

import typer

from savage_trade_evaluator.config import (
    BACKTESTER_END_SEASON,
    BACKTESTER_START_SEASON,
    configure_logging,
)
from savage_trade_evaluator.ingest import transactions
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
    typer.echo(f"total transactions:        {count[0]}")
    typer.echo(f"trade events (all):        {trade_events[0] if trade_events else 0}")
    typer.echo(f"trade events (MLB-only):   {affiliated[0] if affiliated else 0}")
    typer.echo("per-season transactions:")
    for s, n in seasons:
        typer.echo(f"  {s}: {n}")
