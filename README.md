# savage-trade-evaluator

Context-aware MLB trade valuation. Same player → N valuations, one per acquiring club's contention window, payroll situation, farm depth, positional need, dev-system fit.

Planning brief: `~/.claude/plans/we-re-starting-from-the-smooth-iverson.md`. Decisions log: `~/Vault/savage_vault/wiki/trade-eval--decisions.md`. Vault book notes: `~/Vault/savage_vault/wiki/{lindbergh,click-keri,lewis,mcelreath,cunningham}-*.md`.

## Quick start

```bash
uv sync                                       # install
uv run ste init                               # schema + teams + views

# Ingest the V1 data spine
uv run ste ingest transactions                # MLB Stats API trades, 1990-2024 (~30s)
uv run ste ingest bwar                        # Baseball Reference WAR, all-time (~10s)
uv run ste ingest statcast                    # Baseball Savant 2015-2024 (~10s)
uv run ste ingest coaches                     # MLB API coaches per team-season (~3min)
uv run ste ingest front-office                # BR front-office 2010-2024 (~25min, rate-limited)

uv run ste status                             # what landed
```

## Catalog

Browse known stat sources and what's currently ingested / available / blocked:

```bash
uv run ste catalog                            # all 24 entries
uv run ste catalog --status ingested          # active adapters only
uv run ste catalog --status available         # known sources without adapters yet
uv run ste catalog --status blocked           # FanGraphs etc.
uv run ste catalog --search spin              # substring search
```

See [`docs/STATS_CATALOG.md`](docs/STATS_CATALOG.md) for the human-browsable mirror.

## Analyze

Read-only queries on top of the V1 data:

```bash
uv run ste analyze scope --min-war 2.0        # Q-01 scope-cutoff exploration
uv run ste analyze dev-fit-jumps --season 2018 --top 10
uv run ste analyze personnel 371509           # Pressly trade full personnel snapshot
```

## V1 design docs

- [`docs/STATS_CATALOG.md`](docs/STATS_CATALOG.md) — registry of stat sources
- [`docs/NAIVE_BASELINE.md`](docs/NAIVE_BASELINE.md) — the baseline model we want to beat

## Layout

```
src/savage_trade_evaluator/
├── config.py                  # paths, settings, logging
├── cli.py                     # typer CLI
├── ingest/
│   ├── transactions.py        # MLB Stats API trades
│   ├── stats.py               # bWAR + Baseball Savant Statcast
│   ├── coaches.py             # MLB Stats API team coaching staff
│   ├── front_office.py        # BR front-office scrape
│   └── catalog.py             # stat-source registry
├── storage/
│   ├── db.py                  # DuckDB connection context manager
│   ├── schemas.py             # versioned DDL (schema v3)
│   ├── teams.py               # MLB ↔ bWAR team-code mapping
│   ├── trade_views.py         # trade-event SQL views
│   └── outcome_views.py       # metric-agnostic outcome-window views
└── analysis/
    └── trade_summary.py       # read-only analysis helpers
```

Data lands at `data/duckdb/trades.db`. Schema versioned at `src/savage_trade_evaluator/storage/schemas.py`.

## Dev

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pyright src/ tests/
uv run pytest
```
