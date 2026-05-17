"""Typer-based CLI: ``ste ingest transactions --season 2018`` etc."""

from __future__ import annotations

import logging

import typer

from savage_trade_evaluator.analysis import backtest, trade_summary
from savage_trade_evaluator.config import (
    BACKTESTER_END_SEASON,
    BACKTESTER_START_SEASON,
    configure_logging,
)
from savage_trade_evaluator.ingest import (
    catalog,
    coaches,
    draft,
    front_office,
    prospects,
    retrosheet_transactions,
    standings,
    stats,
    transactions,
)
from savage_trade_evaluator.modeling import bayesian, context_aware, features, naive_baseline
from savage_trade_evaluator.storage import db, outcome_views, schemas, teams, trade_views

app = typer.Typer(no_args_is_help=True, help="Savage Trade Evaluator CLI.")
ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion commands.")
analyze_app = typer.Typer(no_args_is_help=True, help="Read-only analysis helpers.")
backtest_app = typer.Typer(
    no_args_is_help=True, help="Backtest harness — run models over historical trades."
)
app.add_typer(ingest_app, name="ingest")
app.add_typer(analyze_app, name="analyze")
app.add_typer(backtest_app, name="backtest")

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


@ingest_app.command("prospects")
def ingest_prospects(
    year: int | None = typer.Option(None, help="Single year to ingest."),
    start: int = typer.Option(2018, help="First year (MLB Pipeline coverage starts ~2018)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last year."),
) -> None:
    """Scrape MLB Pipeline top-100 prospect rankings per year."""
    configure_logging()
    if year is not None:
        n = prospects.ingest_year(year)
        typer.echo(f"ingested {n} prospects for {year}")
    else:
        n = prospects.ingest_range(start, end)
        typer.echo(f"ingested {n} prospects across {end - start + 1} year(s)")


@ingest_app.command("retrosheet-transactions")
def ingest_retrosheet_transactions(
    end_year: int = typer.Option(2009, help="Last season to ingest (default pre-2010 only)."),
) -> None:
    """Ingest pre-2010 trades from Retrosheet to fill the MLB Stats API gap."""
    configure_logging()
    n = retrosheet_transactions.ingest(end_year=end_year)
    typer.echo(f"ingested {n} retrosheet trade-leg rows through {end_year}")


@ingest_app.command("draft")
def ingest_draft(
    year: int | None = typer.Option(None, help="Single draft year to ingest."),
    start: int = typer.Option(1990, help="First draft year (MLB Stats API coverage)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last draft year."),
) -> None:
    """Ingest MLB Draft picks per year from the MLB Stats API."""
    configure_logging()
    if year is not None:
        n = draft.ingest_year(year)
        typer.echo(f"ingested {n} draft picks for {year}")
    else:
        n = draft.ingest_range(start, end)
        typer.echo(f"ingested {n} draft picks across {end - start + 1} year(s)")


@ingest_app.command("standings")
def ingest_standings(
    season: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(BACKTESTER_START_SEASON, help="First season."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season."),
) -> None:
    """Pull final-standings per season via pybaseball.standings()."""
    configure_logging()
    seasons = [season] if season else list(range(start, end + 1))
    total = 0
    for s in seasons:
        total += standings.ingest_season(s)
    typer.echo(f"ingested {total} standings rows across {len(seasons)} season(s)")


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


@app.command(name="features")
def compute_features() -> None:
    """Compute team-season context features for the V2 model.

    Aggregates bWAR by (team, season) into hitting and pitching dev-fit
    proxies plus a prior-year-war column. Persists to ``team_season_features``.
    """
    configure_logging()
    n = features.compute_all()
    typer.echo(f"computed {n} team-season feature rows")


@backtest_app.command("naive")
def backtest_naive(
    start: int = typer.Option(BACKTESTER_START_SEASON, help="First trade season (inclusive)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last trade season (inclusive)."),
    window: int = typer.Option(3, help="Outcome-window length in years (T+1..T+N)."),
) -> None:
    """Run the naïve WAR-surplus baseline over historical trades.

    Stores per-(trade_event, team) results in ``naive_baseline_results``.
    """
    configure_logging()
    n = backtest.run_naive_baseline(start_season=start, end_season=end, outcome_window_years=window)
    typer.echo(f"naïve baseline: {n} rows written (window={window}y)")


@backtest_app.command("show")
def backtest_show(
    season: int | None = typer.Option(None, help="Filter to one season."),
    top: int = typer.Option(10, help="Top/bottom N to show."),
    side: str = typer.Option("both", help="'top', 'bottom', or 'both'."),
) -> None:
    """Show biggest WAR wins / losses from the latest backtest."""
    configure_logging()
    if side in ("top", "both"):
        typer.echo(f"=== top {top} naïve-baseline WAR-surplus rows ===")
        df = backtest.top_surpluses(season=season, top_n=top)
        if df.empty:
            typer.echo("(no rows — run `ste backtest naive` first)")
            return
        typer.echo(df.to_string(index=False, max_colwidth=60))
        typer.echo()
    if side in ("bottom", "both"):
        typer.echo(f"=== bottom {top} naïve-baseline WAR-surplus rows ===")
        df = backtest.bottom_surpluses(season=season, top_n=top)
        typer.echo(df.to_string(index=False, max_colwidth=60))


@backtest_app.command("dist")
def backtest_dist() -> None:
    """Per-season distribution summary of naïve-baseline surpluses."""
    configure_logging()
    df = backtest.surplus_distribution()
    typer.echo(df.to_string(index=False))


@backtest_app.command("context")
def backtest_context(
    test_start: int = typer.Option(2021, help="First test season (out-of-time split)."),
) -> None:
    """Fit + evaluate the V0 context-aware OLS model.

    Reports test-set MAE vs the predict-zero baseline.
    """
    configure_logging()
    result = context_aware.fit(test_start_season=test_start)
    typer.echo(f"OLS fit on {result.n_train} train rows, {result.n_test} test rows")
    typer.echo(f"intercept: {result.intercept:+.4f}")
    for col, coef in zip(result.feature_columns, result.coefficients, strict=True):
        typer.echo(f"  coef {col:30s}: {coef:+.5f}")
    typer.echo()
    typer.echo(f"train MAE:                   {result.train_mae:.4f}")
    typer.echo(f"test MAE (context-aware):    {result.test_mae:.4f}")
    typer.echo(f"test MAE (predict-zero):     {result.naive_zero_mae_test:.4f}")
    delta = result.naive_zero_mae_test - result.test_mae
    pct = 100.0 * delta / result.naive_zero_mae_test if result.naive_zero_mae_test else 0.0
    typer.echo(f"improvement over predict-0:  {delta:+.4f} WAR  ({pct:+.2f}%)")


@backtest_app.command("bayesian")
def backtest_bayesian(
    test_start: int = typer.Option(2021, help="First test season (out-of-time split)."),
    samples: int = typer.Option(1000, help="MCMC posterior samples per chain."),
    tune: int = typer.Option(1000, help="MCMC tuning steps per chain."),
    chains: int = typer.Option(2, help="MCMC chains."),
) -> None:
    """Fit the multilevel varying-intercepts Bayesian model and score on test set.

    Compares MAE + CRPS against the predict-zero benchmark.
    """
    configure_logging()
    result = bayesian.fit_multilevel(
        test_start_season=test_start,
        n_samples=samples,
        n_tune=tune,
        n_chains=chains,
    )
    typer.echo(
        f"multilevel Bayesian: train n={result.n_train}, test n={result.n_test}, "
        f"teams={result.n_teams}"
    )
    typer.echo(f"posterior sigma (mean):    {result.posterior_sigma_mean:.4f}")
    typer.echo(f"posterior tau_team (mean): {result.posterior_tau_team_mean:.4f}")
    typer.echo()
    typer.echo(f"train MAE:                   {result.train_mae:.4f}")
    typer.echo(f"test MAE (Bayesian):         {result.test_mae:.4f}")
    typer.echo(f"test MAE (predict-zero):     {result.naive_zero_test_mae:.4f}")
    mae_delta = result.naive_zero_test_mae - result.test_mae
    mae_pct = 100.0 * mae_delta / result.naive_zero_test_mae if result.naive_zero_test_mae else 0.0
    typer.echo(f"MAE improvement over zero:   {mae_delta:+.4f} ({mae_pct:+.2f}%)")
    typer.echo()
    typer.echo(f"test CRPS (Bayesian):        {result.test_crps:.4f}")
    typer.echo(f"test CRPS (predict-zero):    {result.test_crps_naive_zero:.4f}")
    crps_delta = result.test_crps_naive_zero - result.test_crps
    crps_pct = (
        100.0 * crps_delta / result.test_crps_naive_zero if result.test_crps_naive_zero else 0.0
    )
    typer.echo(f"CRPS improvement over zero:  {crps_delta:+.4f} ({crps_pct:+.2f}%)")


@backtest_app.command("trade")
def backtest_trade(
    trade_event_id: int = typer.Argument(...),
    window: int = typer.Option(3, help="Outcome window years."),
) -> None:
    """Evaluate one trade live (without writing to DB)."""
    configure_logging()
    result = naive_baseline.evaluate(trade_event_id, outcome_window_years=window)
    if result is None:
        typer.echo(f"no MLB-affiliated legs for trade {trade_event_id}")
        return
    typer.echo(
        f"trade {result.trade_event_id} ({result.trade_season}, "
        f"{result.outcome_window_years}y window):"
    )
    for ledger in result.team_ledgers:
        typer.echo(
            f"  {ledger.team_bref}  recv={ledger.war_received:+6.2f}  "
            f"gave={ledger.war_given_up:+6.2f}  surplus={ledger.surplus:+6.2f}"
        )
        typer.echo(f"    received: {', '.join(ledger.players_received) or '(none)'}")
        typer.echo(f"    gave:     {', '.join(ledger.players_given_up) or '(none)'}")
    win = result.winning_team
    if win:
        typer.echo(f"  winner by WAR: {win}")


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
