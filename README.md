# savage-trade-evaluator

Context-aware MLB trade valuation. Same player → N valuations, one per acquiring club's contention window, payroll situation, farm depth, positional need, dev-system fit.

Planning brief: `~/.claude/plans/we-re-starting-from-the-smooth-iverson.md`. Vault notes at `~/Vault/savage_vault/wiki/trade-eval--*.md` and the book ingestion notes from MVP Machine / BBtN / Moneyball / Rethinking / Mixtape.

## Quick start

```bash
uv sync                                       # install
uv run ste init                               # initialize DuckDB schema
uv run ste ingest transactions --season 2018  # one season
uv run ste ingest transactions                # full backtester range (2010-2024)
uv run ste status                             # what landed
```

Data lands at `data/duckdb/trades.db`. Tables versioned in `src/savage_trade_evaluator/storage/schemas.py`.

## Layout

```
src/savage_trade_evaluator/
├── config.py            # paths, settings, logging
├── cli.py               # typer CLI: ste init, ste ingest, ste status
├── ingest/
│   └── transactions.py  # MLB Stats API transactions adapter
└── storage/
    ├── db.py            # DuckDB connection context manager
    └── schemas.py       # versioned DDL
```

## Dev

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pyright src/ tests/
uv run pytest
```
