# Architecture

How the pieces fit and why they are shaped this way. The constraints that drove
these choices are in the [project README](../README.md); this doc is the
mechanics.

## Package layout

```
src/savage_trade_evaluator/     82 files, 23,045 lines
├── ingest/       19 adapters, one per source, plus catalog.py
├── storage/      DuckDB schema, team-code mapping, trade + outcome views
├── modeling/     V3 Bayesian regression, features, valuation, GM profiles
│   └── v2/       archived multilevel model; features and outcomes still used
├── analysis/     backtest harness, org quality, sell-high, trade lookups
├── valuation/    prospect FV to WAR
├── warroom/      strategic brief persistence and export
├── rag/          corpus chunking, embeddings, HNSW store, grounded answers
└── reports/      HTML report generation

frontend/         74 files, 14,290 lines of TypeScript, 10 routes
scripts/          73 files: exporters, pipeline utilities, numbered research rounds
tests/            27 files, 2,296 lines, 154 tests
```

Source to test ratio is 10:1 on the Python side, and the frontend has no tests at
all. Both numbers are in the README's known limitations for a reason.

## Storage

One DuckDB file, `data/duckdb/trades.db`, currently 405MB with 54 base tables and
44 views. `STE_DUCKDB_PATH` overrides the location for alternate worktrees.

DDL lives in `storage/schemas.py` behind `SCHEMA_VERSION`, currently 39. The
rules while V1 is frozen: bump the version on additive DDL, and drop and rebuild
a table when a column constraint changes. There is no in-place `ALTER` path.
Every applied version is recorded in the `schema_version` table with a timestamp.

**The write lock is the thing to know.** DuckDB takes an exclusive lock on the
file. One `ste ingest` blocks every other reader and writer, including a second
process. Ingests must be serialized, and every read path opens with
`read_only=True`.

Two view layers sit on top of the tables:

- `storage/trade_views.py` builds trade-event-level views: `trade_movements`
  (19,020 legs), `trade_events` (9,943), `trade_events_affiliated` (7,856).
- `storage/outcome_views.py` builds one parallel window view per metric, each
  exposing T-1 / T / T+1 / T+2 / T+3 for any trade leg. WAR, xwOBA, xERA, and
  arsenal percentile views all share the same interface, which is what lets the
  model treat the outcome variable as a parameter instead of a hardcoded target.

## Ingest

Each source gets one adapter in `ingest/` and one `StatSource` entry in
`ingest/catalog.py`. The catalog is a frozen-dataclass registry of 50 sources
carrying granularity, era, fetcher path, target table, and `ingested` /
`blocked` flags. Catalog the source before wiring the adapter, so the
what-is-possible view stays accurate.

Adapter conventions that came out of the rate-limit constraint:

- Rate limits are respected, not worked around. `ingest/front_office.py` sits at
  3.5 seconds per request per Baseball Reference's guidelines.
- Raw pulls cache to disk (`data/fangraphs_cache/`, `data/prospect_fv_cache/`,
  `data/retrosheet_events/`) so a failed run never re-scrapes.
- Bulk inserts register a pandas DataFrame and run
  `INSERT ... SELECT ... ON CONFLICT` rather than looping `conn.execute()`. The
  per-row path took 68 seconds for 62,800 transactions; the staging path takes
  about 1.
- Season-keyed sources use partition-replace so a re-ingest of one season does
  not disturb the others.

## Modeling

`modeling/v3.py` is the production model: single-level Bayesian regression with a
Student-t likelihood, fit per outcome. It replaced V2's multilevel structure
after R-33, R-34, and R-35 each found that pooling on team or on front-office
regime added no predictive signal over a flat population intercept.

Nine outcomes are defined, each with its own feature subset:

| Outcome group | Outcomes | Features |
|---|---|---|
| Large-n | `war_delta`, `dollar_surplus`, `surplus_wins` | 34 (all) |
| Small-n | `xwoba_delta`, `kpct_delta`, `wrc_delta`, `fip_delta`, `xfip_delta`, `siera_delta` | 25 (acquired-player only) |

The split is empirical, from R-35: the small-n outcomes overfit on
team-aggregate features, so they get the player-only subset.

Outcome windows differ by outcome. `war_delta` and `surplus_wins` run T+2 to T+5,
skipping the transition year, because the season a player changes teams is mostly
playing-time disruption. `dollar_surplus` keeps T+1 to T+3, because cap
obligations in year one are real.

`modeling/production_fit.py` caches posterior traces as NetCDF under
`data/model_cache/`, keyed `{outcome}_v{MODEL_VERSION}_schema{SCHEMA_VERSION}.nc`
with a JSON sidecar holding normalization stats. A version mismatch on either key
invalidates the cache. This is what makes the product interactive: a cold fit is
31 to 33 seconds, a cached load is 0.13.

`modeling/scenario_engine.py` adds two things on top of a prediction. A coverage
report counts pre-imputation NaNs per outcome and grades the row A to D, and
`attribute_score` decomposes a score into per-feature contributions
(`beta_mean_i * x_z_i * y_std`), flagging each as observed or imputed. Both ride
along in the scenario payload so the UI can show when it is extrapolating.

## Product surface

The CLI (`ste`) is the Python entry point: 9 top-level commands and 8 sub-apps
(`ingest`, `analyze`, `backtest`, `v2`, `v3`, `report`, `brief`, `research`).
`score-trade` and `suggest-trades` both run through `assemble_hypothetical` and
`score_hypothetical` against the cached V3 fit.

The frontend never calls Python at runtime. `scripts/export_*.py` read DuckDB and
write typed JSON into `frontend/src/data/`, which the SPA hydrates at build time.
That is what lets the whole product run from a clone with no database.

The War Room's AI brief crosses the boundary as a file, not an API call: a skill
writes `frontend/public/brief-inbox/<TEAM>.json` and the app polls for it.
`warroom/briefs.py` persists and re-exports them (`ste brief ingest` /
`ste brief export`).

## Retrieval

`rag/` indexes the project's own documentation: the four research-log parts plus
the synthesis, baseline, catalog, protocol, and archived design docs. 214 chunks
across 10 files, with the vault wiki appended when present.

Chunking is heading-aware with a word-windowed overlap so each chunk keeps a
citable heading trail. Embeddings come from `model2vec`
(`minishlab/potion-base-8M`, 256 dimensions), which is static and CPU-only and
needs no API key, behind a swappable `Embedder` protocol. The index is a DuckDB
`vss` HNSW index with cosine distance, model-version pinned. Generation falls
back to retrieval-only output when no LLM key is set, so the model never answers
without retrieved context.

## Where state lives

| State | Location | Rebuilt by |
|---|---|---|
| Ingested data | `data/duckdb/trades.db` | `ste ingest <source>` |
| Posterior traces | `data/model_cache/*.nc` | automatic on version bump |
| Raw source pulls | `data/*_cache/` | delete to force a re-scrape |
| Frontend seeds | `frontend/src/data/` | `scripts/export_*.py` |
| RAG index | `data/duckdb/research_rag.db` | `ste research index` |
| Data-quality baseline | `data/check_baseline.json` | `ste check` |
