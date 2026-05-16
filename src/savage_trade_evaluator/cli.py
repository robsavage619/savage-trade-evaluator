"""Typer-based CLI: ``ste ingest transactions --season 2018`` etc."""

from __future__ import annotations

import logging

import typer

from savage_trade_evaluator.analysis import trade_summary
from savage_trade_evaluator.config import (
    BACKTESTER_END_SEASON,
    BACKTESTER_START_SEASON,
    configure_logging,
)
from savage_trade_evaluator.ingest import catalog, coaches, front_office, stats, transactions
from savage_trade_evaluator.storage import db, outcome_views, schemas, teams, trade_views

app = typer.Typer(no_args_is_help=True, help="Savage Trade Evaluator CLI.")
ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion commands.")
analyze_app = typer.Typer(no_args_is_help=True, help="Read-only analysis helpers.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(analyze_app, name="analyze")

logger = logging.getLogger(__name__)


@app.command()
def init() -> None:
    """Initialize the DuckDB schema, teams mapping, and trade-event views."""
    configure_logging()
    with db.connect() as conn:
        schemas.initialize(conn)
        teams.initialize(conn)
        trade_views.create_all(conn)
        outcome_views.create_all(conn)
    typer.echo("schema initialized")


@app.command(name="catalog")
def catalog_(
    status: str = typer.Option(
        "all",
        help="Filter: 'all', 'ingested', 'available', 'blocked'.",
    ),
    source: str | None = typer.Option(None, help="Filter by source (e.g. 'baseball-savant')."),
    search: str | None = typer.Option(None, help="Substring search across name/notes/columns."),
) -> None:
    """List available stat sources from the catalog.

    Browse what we can pull in. The catalog lives in
    ``src/savage_trade_evaluator/ingest/catalog.py``; this command is a
    convenience for exploring it from the shell.
    """
    if status == "ingested":
        entries = catalog.ingested()
    elif status == "available":
        entries = catalog.available_not_yet_ingested()
    elif status == "blocked":
        entries = catalog.blocked()
    else:
        entries = list(catalog.CATALOG)

    if source:
        entries = [e for e in entries if e.source == source]
    if search:
        needle = search.lower()
        entries = [
            e
            for e in entries
            if needle in (e.name + " " + e.notes + " " + " ".join(e.primary_columns)).lower()
        ]

    if not entries:
        typer.echo("(no matching catalog entries)")
        return
    for e in entries:
        flag = "✅" if e.ingested else ("⛔" if e.blocked else "☐ ")
        era_end = e.era_end if e.era_end else "now"
        typer.echo(
            f"{flag} {e.name:<40} {e.source:<18} {e.granularity:<22} {e.era_start}-{era_end}"
        )
        if e.notes:
            typer.echo(f"    {e.notes}")


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


@ingest_app.command("coaches")
def ingest_coaches(
    season: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(2010, help="First season (coaches endpoint coverage starts ~2010)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season."),
) -> None:
    """Pull team coaching staff (manager + assistants) per team-season from MLB Stats API."""
    configure_logging()
    seasons = [season] if season else list(range(start, end + 1))
    total = 0
    for s in seasons:
        total += coaches.ingest_season(s)
    typer.echo(f"ingested {total} coach rows across {len(seasons)} season(s)")


@ingest_app.command("front-office")
def ingest_front_office(
    season: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(2010, help="First season."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season."),
) -> None:
    """Scrape front-office personnel (GM, POBO, Farm/Scouting Director) from Baseball Reference.

    Rate-limited per BR guidelines; expect ~25 minutes for a full 2010-2024 ingest.
    """
    configure_logging()
    seasons = [season] if season else list(range(start, end + 1))
    total = 0
    for s in seasons:
        total += front_office.ingest_season_all_teams(s)
    typer.echo(f"ingested {total} front-office rows across {len(seasons)} season(s)")


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


@analyze_app.command("scope")
def analyze_scope(min_war: float = typer.Option(2.0, help="Minimum prior-season WAR")) -> None:
    """Count of trade events per season for various Q-01 scope cutoffs.

    Helps answer Q-01 (what counts as a 'meaningful' trade for the backtester).
    """
    configure_logging()
    all_trades = trade_summary.trades_per_season()
    war_trades = trade_summary.trades_with_war_player(min_war)
    typer.echo(f"{all_trades.label}: total = {all_trades.total()}")
    typer.echo(f"{war_trades.label}: total = {war_trades.total()}")
    typer.echo()
    typer.echo(f"{'season':>8s}  {'all':>5s}  {'≥' + str(min_war) + ' WAR':>10s}")
    for s in sorted(all_trades.counts_by_season):
        typer.echo(
            f"{s:>8d}  {all_trades.counts_by_season.get(s, 0):>5d}  "
            f"{war_trades.counts_by_season.get(s, 0):>10d}"
        )


@analyze_app.command("dev-fit-jumps")
def analyze_dev_fit_jumps(
    season: int = typer.Option(2018, help="Season of trades to analyze."),
    top: int = typer.Option(10, help="Number of biggest jumps to show."),
) -> None:
    """Pitchers traded in `season` ranked by post-trade K-percentile jump."""
    configure_logging()
    df = trade_summary.biggest_dev_fit_jumps(season=season, top_n=top)
    if df.empty:
        typer.echo("(no matching trades)")
        return
    typer.echo(df.to_string(index=False))


@analyze_app.command("personnel")
def analyze_personnel(trade_event_id: int = typer.Argument(...)) -> None:
    """Show both-sides personnel snapshot for one trade event."""
    configure_logging()
    snapshot = trade_summary.personnel_for_trade(trade_event_id)
    if not snapshot:
        typer.echo(f"no trade event with id {trade_event_id}")
        return
    for side, df in snapshot.items():
        typer.echo(f"--- {side} ---")
        typer.echo(df.to_string(index=False))
        typer.echo()


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
