"""Typer-based CLI: ``ste ingest transactions --season 2018`` etc."""

from __future__ import annotations

import json
import logging
import webbrowser
from pathlib import Path

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
    fangraphs_leaders,
    fortification,
    front_office,
    milb_stats,
    mlb_pipeline,
    prospects,
    retrosheet_gamelogs,
    retrosheet_transactions,
    spotrac,
    standings,
    statcast_extended,
    stats,
    tjstats,
    transactions,
)
from savage_trade_evaluator.modeling import bayesian, context_aware, features, naive_baseline
from savage_trade_evaluator.modeling import v3 as v3_module
from savage_trade_evaluator.modeling.v2 import backtest as v2_backtest
from savage_trade_evaluator.storage import db, outcome_views, schemas, teams, trade_views

app = typer.Typer(no_args_is_help=True, help="Savage Trade Evaluator CLI.")
ingest_app = typer.Typer(no_args_is_help=True, help="Ingestion commands.")
analyze_app = typer.Typer(no_args_is_help=True, help="Read-only analysis helpers.")
backtest_app = typer.Typer(
    no_args_is_help=True, help="Backtest harness — run models over historical trades."
)
v2_app = typer.Typer(
    no_args_is_help=True, help="V2 multilevel-model commands (deprecated — see R-33/34/35)."
)
v3_app = typer.Typer(no_args_is_help=True, help="V3 single-level Bayesian regression (current).")
report_app = typer.Typer(no_args_is_help=True, help="Generate HTML research reports.")
brief_app = typer.Typer(no_args_is_help=True, help="War Room AI brief persistence + export.")
research_app = typer.Typer(
    no_args_is_help=True, help="RAG over the research corpus (vector retrieval + grounded answers)."
)
app.add_typer(ingest_app, name="ingest")
app.add_typer(analyze_app, name="analyze")
app.add_typer(backtest_app, name="backtest")
app.add_typer(v2_app, name="v2")
app.add_typer(v3_app, name="v3")
app.add_typer(report_app, name="report")
app.add_typer(brief_app, name="brief")
app.add_typer(research_app, name="research")

V2_OUTCOMES: tuple[str, ...] = ("xwoba_delta", "kpct_delta", "war_delta", "dollar_surplus")

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


@brief_app.command("ingest")
def brief_ingest(
    team: str = typer.Argument(..., help="Team code, e.g. NYM."),
    file: Path = typer.Option(..., "--file", "-f", help="Path to the brief JSON."),
    model: str | None = typer.Option(None, "--model", help="Model that generated it."),
    source: str = typer.Option("skill", "--source", help="Origin: skill | app | manual."),
) -> None:
    """Persist a generated brief into DuckDB and write the frontend inbox file."""
    configure_logging()
    from savage_trade_evaluator.warroom import briefs

    brief = json.loads(file.read_text())
    out = briefs.save_brief(team, brief, model=model, source=source)
    typer.echo(f"brief ingested for {team.upper()} -> DuckDB war_room_briefs + {out}")


@brief_app.command("export")
def brief_export(
    team: str | None = typer.Option(None, "--team", help="Team code to export."),
    all_teams: bool = typer.Option(False, "--all", help="Export the latest brief for every team."),
) -> None:
    """Re-emit stored brief(s) from DuckDB to the frontend inbox."""
    configure_logging()
    from savage_trade_evaluator.warroom import briefs

    if all_teams:
        count = briefs.export_all()
        typer.echo(f"exported {count} brief(s)")
    elif team:
        ok = briefs.export_brief(team)
        typer.echo("exported" if ok else f"no stored brief for {team.upper()}")
    else:
        raise typer.BadParameter("provide --team CODE or --all")


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


@ingest_app.command("milb")
def ingest_milb(
    season: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(2010, help="First season (inclusive)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season (inclusive)."),
    sport_ids: str = typer.Option(
        "11,12,13,14",
        help="Comma-separated MLB sportIds (11=AAA, 12=AA, 13=Hi-A, 14=Lo-A).",
    ),
) -> None:
    """Pull MiLB hitting + pitching seasonal stats from the MLB Stats API.

    Defaults to all four full-season minor leagues, 2010 → current backtester end.
    """
    configure_logging()
    sports = tuple(int(s) for s in sport_ids.split(",") if s.strip())
    seasons = [season] if season else list(range(start, end + 1))
    total = 0
    for s in seasons:
        total += milb_stats.ingest_season(s, sport_ids=sports)
    typer.echo(f"ingested {total} milb rows across {len(seasons)} season(s)")


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
    start: int = typer.Option(2017, help="First year of FanGraphs The Board cache."),
    end: int = typer.Option(2026, help="Last year."),
) -> None:
    """Load FanGraphs The Board FV grades from data/prospect_fv_cache/ CSVs."""
    configure_logging()
    if year is not None:
        n = prospects.ingest_year(year)
        typer.echo(f"ingested {n} prospect FV rows for {year}")
    else:
        n = prospects.ingest_range(start, end)
        typer.echo(f"ingested {n} prospect FV rows across {end - start + 1} year(s)")


@ingest_app.command("fangraphs")
def ingest_fangraphs(
    stats: str = typer.Option("both", help="'bat', 'pit', or 'both'."),
    year: int | None = typer.Option(None, help="Single season to ingest."),
    start: int = typer.Option(2010, help="First season."),
    end: int = typer.Option(2024, help="Last season."),
    from_cache: bool = typer.Option(
        False,
        "--from-cache",
        help="Read cached Firecrawl responses from data/fangraphs_cache/ "
        "instead of fetching via the REST API (no FIRECRAWL_API_KEY needed).",
    ),
) -> None:
    """Load FanGraphs batting/pitching leaderboards.

    Two paths: live REST fetch via the Firecrawl stealth proxy (needs
    FIRECRAWL_API_KEY), or --from-cache to parse responses already saved to
    data/fangraphs_cache/{stats}_{season}.json (fetched via the Firecrawl MCP).
    """
    configure_logging()
    types = ("bat", "pit") if stats == "both" else (stats,)
    if year is not None:
        for s in types:
            n = (
                fangraphs_leaders.ingest_from_cache(s, year)
                if from_cache
                else fangraphs_leaders.ingest_year(s, year)
            )
            typer.echo(f"fangraphs {s} {year}: {n} rows")
    else:
        results = (
            fangraphs_leaders.ingest_range_from_cache(types, start, end)
            if from_cache
            else fangraphs_leaders.ingest_range(types, start, end)
        )
        for k, v in results.items():
            typer.echo(f"fangraphs {k}: {v} rows")


@ingest_app.command("mlb-pipeline")
def ingest_mlb_pipeline(
    no_grades: bool = typer.Option(
        False, "--no-grades", help="Skip per-player scouting-report fetches (faster)."
    ),
) -> None:
    """Fetch MLB Pipeline current top-100 + 20-80 scouting grades (mlb.com, public)."""
    configure_logging()
    n = mlb_pipeline.ingest(with_grades=not no_grades)
    typer.echo(f"mlb-pipeline: {n} prospect rows ingested")


@ingest_app.command("tjstats")
def ingest_tjstats() -> None:
    """Fetch TJStats rankings + scouting grades (live WP JSON API)."""
    configure_logging()
    totals = tjstats.ingest_all()
    for endpoint, n in totals.items():
        typer.echo(f"tjstats/{endpoint}: {n} rows ingested")


@ingest_app.command("game-logs")
def ingest_game_logs(
    year: int | None = typer.Option(None, help="Single year."),
    start: int = typer.Option(1990, help="First year."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last year."),
) -> None:
    """Ingest Retrosheet per-game logs (date, teams, scores, attendance, park, etc.)."""
    configure_logging()
    if year is not None:
        n = retrosheet_gamelogs.ingest_year(year)
        typer.echo(f"ingested {n} games for {year}")
    else:
        n = retrosheet_gamelogs.ingest_range(start=start, end=end)
        typer.echo(f"ingested {n} games across {end - start + 1} seasons")


@ingest_app.command("retrosheet-transactions")
def ingest_retrosheet_transactions(
    end_year: int = typer.Option(2009, help="Last season to ingest (default pre-2010 only)."),
) -> None:
    """Ingest pre-2010 trades from Retrosheet to fill the MLB Stats API gap."""
    configure_logging()
    n = retrosheet_transactions.ingest(end_year=end_year)
    typer.echo(f"ingested {n} retrosheet trade-leg rows through {end_year}")


@ingest_app.command("spotrac")
def ingest_spotrac(
    year: int | None = typer.Option(None, help="Single season."),
    start: int = typer.Option(2011, help="First season (Spotrac coverage)."),
    end: int = typer.Option(2025, help="Last season."),
    team: str | None = typer.Option(None, help="Single team bref_code (e.g. LAD)."),
) -> None:
    """Ingest MLB player contracts + team payrolls from Spotrac."""
    configure_logging()
    teams = (team,) if team else None
    if year is not None:
        n = spotrac.ingest_year(year, team_filter=teams)
    else:
        n = spotrac.ingest_range(start=start, end=end)
    typer.echo(f"ingested {n} spotrac contract rows")


@ingest_app.command("team-season-stats")
def ingest_team_season_stats(
    start: int = typer.Option(1990, help="First season."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season."),
) -> None:
    """Ingest per-team per-season hitting/pitching/fielding aggregates."""
    configure_logging()
    n = fortification.ingest_team_season_stats_range(start=start, end=end)
    typer.echo(f"ingested {n} team-season-stat rows")


@ingest_app.command("venues")
def ingest_venues() -> None:
    """Ingest MLB Stats API venues (capacity, dimensions, turf, roof)."""
    configure_logging()
    n = fortification.ingest_mlb_venues()
    typer.echo(f"ingested {n} venue rows")


@ingest_app.command("parks")
def ingest_parks() -> None:
    """Ingest Retrosheet parkcode.txt — historical park metadata."""
    configure_logging()
    n = fortification.ingest_retrosheet_parks()
    typer.echo(f"ingested {n} park rows")


@ingest_app.command("pitch-movement")
def ingest_pitch_movement(
    start: int = typer.Option(2015, help="First year."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last year."),
) -> None:
    """Ingest Statcast pitch-movement leaderboard across all pitch types."""
    configure_logging()
    n = fortification.ingest_pitch_movement_range(start=start, end=end)
    typer.echo(f"ingested {n} pitch-movement rows")


@ingest_app.command("rosters")
def ingest_rosters(
    start: int = typer.Option(2010, help="First season."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season."),
) -> None:
    """Ingest team 40-man rosters from MLB Stats API."""
    configure_logging()
    n = fortification.ingest_rosters_range(start=start, end=end)
    typer.echo(f"ingested {n} roster rows")


@ingest_app.command("mlb-people")
def ingest_mlb_people() -> None:
    """Pull MLB Stats API /people for every player in our bWAR table.

    Provides birth country, bat side, pitch hand, height, weight, position,
    MLB debut date. The cleaner replacement for our 'post-1995 non-drafted'
    international-signing proxy.
    """
    configure_logging()
    n = fortification.ingest_people_for_all_bwar_players()
    typer.echo(f"ingested {n} mlb_people rows")


@ingest_app.command("chadwick")
def ingest_chadwick() -> None:
    """Ingest the Chadwick player register (birth dates + ID cross-walks)."""
    configure_logging()
    n = fortification.ingest_chadwick_register()
    typer.echo(f"ingested {n} chadwick register rows")


@ingest_app.command("catcher-framing")
def ingest_catcher_framing(
    year: int | None = typer.Option(None, help="Single year."),
    start: int = typer.Option(2015, help="First year."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last year."),
) -> None:
    """Ingest Statcast catcher framing leaderboard from Baseball Savant."""
    configure_logging()
    if year is not None:
        n = fortification.ingest_catcher_framing_range(start=year, end=year)
    else:
        n = fortification.ingest_catcher_framing_range(start=start, end=end)
    typer.echo(f"ingested {n} catcher framing rows")


@ingest_app.command("awards")
def ingest_awards(
    start: int = typer.Option(1990, help="First season."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last season."),
) -> None:
    """Ingest MVP/Cy Young/ROY/Gold Glove/Silver Slugger recipients from MLB Stats API."""
    configure_logging()
    n = fortification.ingest_awards_range(start=start, end=end)
    typer.echo(f"ingested {n} award-recipient rows")


@ingest_app.command("statcast-extended")
def ingest_statcast_extended(
    year: int | None = typer.Option(None, help="Single year to ingest."),
    start: int = typer.Option(2015, help="First year (Statcast era begins)."),
    end: int = typer.Option(BACKTESTER_END_SEASON, help="Last year."),
) -> None:
    """Ingest batter percentile ranks + pitcher arsenal stats + OAA from Savant."""
    configure_logging()
    if year is not None:
        totals = statcast_extended.ingest_all_for_year(year)
    else:
        totals = statcast_extended.ingest_range(start, end)
    for k, v in totals.items():
        typer.echo(f"  {k}: {v} rows")


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


def _v2_validate_outcome(outcome: str) -> None:
    if outcome not in V2_OUTCOMES:
        msg = f"unknown outcome '{outcome}'; choose from {', '.join(V2_OUTCOMES)}"
        raise typer.BadParameter(msg)


@v2_app.command("fit")
def v2_fit(
    outcome: str = typer.Option(..., help=f"One of: {', '.join(V2_OUTCOMES)}."),
    train_end: int = typer.Option(2020, help="Last season included in training."),
    test_end: int = typer.Option(2024, help="Last test season."),
    minimum_features_present: int = typer.Option(5, help="Min non-null features per row."),
) -> None:
    """Fit + backtest a single V2 outcome and print the report."""
    configure_logging()
    _v2_validate_outcome(outcome)
    result = v2_backtest.backtest_outcome(
        outcome=outcome,
        train_end_season=train_end,
        test_end_season=test_end,
        minimum_features_present=minimum_features_present,
    )
    v2_backtest.print_backtest_report(result)


@v2_app.command("backtest")
def v2_backtest_all(
    outcome: str = typer.Option("all", help="'all' or a specific outcome name."),
    train_end: int = typer.Option(2020, help="Last season included in training."),
    test_end: int = typer.Option(2024, help="Last test season."),
    minimum_features_present: int = typer.Option(5, help="Min non-null features per row."),
) -> None:
    """Run the V2 backtest across one or all outcomes; print summary table."""
    configure_logging()
    if outcome == "all":
        outcomes: tuple[str, ...] = V2_OUTCOMES
    else:
        _v2_validate_outcome(outcome)
        outcomes = (outcome,)

    results = {}
    for o in outcomes:
        typer.echo("")
        typer.echo("#" * 88)
        typer.echo(f"# {o.upper()}")
        typer.echo("#" * 88)
        try:
            result = v2_backtest.backtest_outcome(
                outcome=o,
                train_end_season=train_end,
                test_end_season=test_end,
                minimum_features_present=minimum_features_present,
            )
        except ValueError as e:
            typer.echo(f"  SKIPPED: {e}")
            continue
        v2_backtest.print_backtest_report(result)
        results[o] = result

    typer.echo("")
    typer.echo("=" * 88)
    typer.echo("SUMMARY")
    typer.echo("=" * 88)
    for o, r in results.items():
        ncred = int(r.credible_features["credible"].sum())
        typer.echo(
            f"  {o:<16} train={r.train_n:>4} test={r.test_n:>4}  "
            f"MAE={r.test_mae:.4f}  CRPS={r.test_crps:.4f}  "
            f"cov90={r.coverage_90:.1%}  credible_features={ncred}"
        )


@v2_app.command("predict")
def v2_predict(
    trade_id: int = typer.Option(..., help="trade_event_id to predict for."),
    receiver: str = typer.Option(..., help="Receiver team bref code (e.g. 'HOU')."),
    outcome: str = typer.Option(..., help=f"One of: {', '.join(V2_OUTCOMES)}."),
    train_end: int = typer.Option(2024, help="Last season included in the fit."),
    minimum_features_present: int = typer.Option(5, help="Min non-null features per row."),
) -> None:
    """Posterior prediction for one (trade_event_id, receiver) under a fitted V2 model."""
    import numpy as np

    configure_logging()
    _v2_validate_outcome(outcome)
    # Fit on full history through train_end (test set used internally is ignored
    # — we just need the posterior).
    result = v2_backtest.backtest_outcome(
        outcome=outcome,
        train_end_season=train_end,
        test_end_season=train_end,
        minimum_features_present=minimum_features_present,
    )
    fit = result.fit

    combined = v2_backtest.assemble_combined()
    combined = combined[combined[outcome].notna()].copy()
    cols = list(fit.feature_cols)
    for c in cols:
        combined[c] = combined[c].astype("float64")
        combined[c] = combined[c].fillna(combined[c].mean())
    row = combined[
        (combined["trade_event_id"] == trade_id) & (combined["receiver_bref"] == receiver)
    ]
    if row.empty:
        typer.echo(f"no row found for trade_id={trade_id} receiver={receiver} outcome={outcome}")
        raise typer.Exit(code=1)

    r = row.iloc[0]
    x_row = ((row[cols] - fit.feature_means) / fit.feature_stds).to_numpy(dtype=float)[0]
    post = fit.trace.posterior
    n = post["alpha0"].shape[0] * post["alpha0"].shape[1]
    alpha0_s = post["alpha0"].values.reshape(n)
    beta_s = post["beta"].values.reshape(n, len(cols))
    alpha_regime_s = post["alpha_regime"].values.reshape(n, len(fit.regimes))
    regime_idx = {rg: i for i, rg in enumerate(fit.regimes)}.get(r["regime_id"], -1)
    team_alpha = alpha_regime_s[:, regime_idx] if regime_idx >= 0 else 0.0
    mu_z = alpha0_s + team_alpha + beta_s @ x_row
    samples = mu_z * fit.y_std + fit.y_mean
    typer.echo(f"trade_id={trade_id}  receiver={receiver}  outcome={outcome}")
    typer.echo(f"  true:            {r[outcome]:+.4f}")
    typer.echo(f"  posterior mean:  {float(samples.mean()):+.4f}")
    typer.echo(
        f"  90% CI:          "
        f"[{float(np.percentile(samples, 5)):+.4f}, "
        f"{float(np.percentile(samples, 95)):+.4f}]"
    )
    typer.echo(f"  regime:          {r['regime_id']}")


@v3_app.command("fit")
def v3_fit(
    outcome: str = typer.Option(..., help=f"One of: {', '.join(V2_OUTCOMES)}."),
    train_end: int = typer.Option(2020, help="Last training season."),
    test_end: int = typer.Option(2024, help="Last test season."),
) -> None:
    """Fit + backtest one V3 outcome and print the report."""
    configure_logging()
    _v2_validate_outcome(outcome)
    result = v3_module.backtest_outcome_v3(
        outcome=outcome,
        train_end_season=train_end,
        test_end_season=test_end,
    )
    v3_module.print_backtest_report(result)


@v3_app.command("backtest")
def v3_backtest_all(
    outcome: str = typer.Option("all", help="'all' or a specific outcome name."),
    train_end: int = typer.Option(2020, help="Last training season."),
    test_end: int = typer.Option(2024, help="Last test season."),
) -> None:
    """Run V3 backtest across one or all outcomes; print summary table."""
    configure_logging()
    if outcome == "all":
        outcomes: tuple[str, ...] = V2_OUTCOMES
    else:
        _v2_validate_outcome(outcome)
        outcomes = (outcome,)

    results = {}
    for o in outcomes:
        typer.echo("")
        typer.echo("#" * 88)
        typer.echo(f"# {o.upper()}")
        typer.echo("#" * 88)
        try:
            result = v3_module.backtest_outcome_v3(
                outcome=o,
                train_end_season=train_end,
                test_end_season=test_end,
            )
        except ValueError as e:
            typer.echo(f"  SKIPPED: {e}")
            continue
        v3_module.print_backtest_report(result)
        results[o] = result

    typer.echo("")
    typer.echo("=" * 88)
    typer.echo("SUMMARY")
    typer.echo("=" * 88)
    for o, r in results.items():
        ncred = int(r.credible_features["credible"].sum())
        nfeat = len(r.fit.feature_cols)
        typer.echo(
            f"  {o:<16} train={r.train_n:>4} test={r.test_n:>4}  "
            f"feats={nfeat:>2}  MAE={r.test_mae:.4f}  CRPS={r.test_crps:.4f}  "
            f"cov90={r.coverage_90:.1%}  credible={ncred}"
        )


# ── Report commands ──────────────────────────────────────────────────────────


@report_app.command("findings")
def report_findings(
    out: Path = typer.Option(Path("trade-eval-findings.html"), "--out", help="Output HTML path."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open in browser after generating."
    ),
) -> None:
    """Generate the research findings HTML report (org quality map + sell-high + methodology)."""
    configure_logging()
    from savage_trade_evaluator.reports import builder

    typer.echo("building findings report…")
    path = builder.build_findings_report(out)
    typer.echo(f"wrote {path}")
    if open_browser:
        webbrowser.open(path.resolve().as_uri())


@report_app.command("backtest")
def report_backtest(
    outcome: str = typer.Option("all", "--outcome", help="'all' or a specific outcome name."),
    out: Path = typer.Option(Path("trade-eval-backtest.html"), "--out", help="Output HTML path."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open in browser after generating."
    ),
    train_end: int = typer.Option(2020, "--train-end", help="Last training season."),
    test_end: int = typer.Option(2024, "--test-end", help="Last test season."),
) -> None:
    """Fit V3 across outcomes; emit a calibration + feature-credibility report (slow — MCMC)."""
    configure_logging()
    if outcome == "all":
        outcomes: list[str] = list(V2_OUTCOMES)
    else:
        _v2_validate_outcome(outcome)
        outcomes = [outcome]
    from savage_trade_evaluator.reports import builder

    typer.echo(f"building backtest report for {outcomes}…")
    path = builder.build_backtest_report(
        outcomes=outcomes, out_path=out, train_end=train_end, test_end=test_end
    )
    typer.echo(f"wrote {path}")
    if open_browser:
        webbrowser.open(path.resolve().as_uri())


@research_app.command(name="index")
def research_index() -> None:
    """Build the vector index over the research corpus (RESEARCH_LOG + docs)."""
    configure_logging()
    from savage_trade_evaluator.rag import store
    from savage_trade_evaluator.rag.embed import Model2VecEmbedder

    typer.echo("loading embedder…")
    embedder = Model2VecEmbedder()
    typer.echo("chunking + embedding corpus…")
    n = store.build_index(embedder)
    typer.echo(f"indexed {n} chunks → {store.RAG_DB_PATH}")


@research_app.command(name="ask")
def research_ask(
    question: str = typer.Argument(..., help="Natural-language question about the project."),
    k: int = typer.Option(5, "--k", help="Number of passages to retrieve."),
) -> None:
    """Retrieve the most relevant passages and synthesise a grounded, cited answer.

    Retrieval always runs first. If ANTHROPIC_API_KEY is set, Claude synthesises
    a cited answer from the retrieved passages; otherwise the ranked passages are
    printed directly. The model never answers without retrieved context.
    """
    configure_logging()
    from savage_trade_evaluator.rag import answer, store
    from savage_trade_evaluator.rag.embed import Model2VecEmbedder

    embedder = Model2VecEmbedder()
    hits = store.search(embedder, question, k=k)
    result = answer.synthesise(question, hits)
    typer.echo(result.text)
    if result.generated:
        typer.echo("\nsources:")
        for i, h in enumerate(hits, start=1):
            typer.echo(f"  [{i}] {h.source} > {h.heading}  ({h.score:.3f})")
