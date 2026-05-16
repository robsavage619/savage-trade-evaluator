# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions track the V1/V2 milestones from the planning brief.

## [Unreleased] — V1 data spine

### Added
- Project Claude config: `CLAUDE.md`, `.claude/settings.json`, slash commands `/check`, `/trade <id>`, `/sources`, `/decisions`.
- `LESSONS.md`, `CHANGELOG.md`, `SKILLS.md`.
- `ste analyze` CLI surface with three sub-commands:
  - `scope --min-war X` — Q-01 trade-scope-cutoff exploration per season.
  - `dev-fit-jumps --season Y --top N` — pitchers by K-percentile jump T-1→T+1.
  - `personnel TRADE_ID` — both-sides front-office + coaches snapshot.
- `analysis/trade_summary.py` module exposing read-only summaries from V1 data.
- `docs/NAIVE_BASELINE.md` design — the baseline we want to beat.
- `docs/STATS_CATALOG.md` — human-browsable mirror of the source registry.
- Parser regression tests (5 for BR front-office, 4 for MLB API coaches normalization).
- **`ingest/front_office.py`** — Baseball Reference per-season team-page scraper for GM + President of Baseball Ops + Farm Director + Scouting Director. Rate-limited at 3.5s per request. 1,880 rows for 2010-2024.
- **`ingest/coaches.py`** — MLB Stats API `/teams/{id}/coaches` per team-season. Manager + bench/hitting/pitching/bullpen/base coaches. 5,408 rows for 2010-2024.
- **`storage/outcome_views.py`** with parallel windows for WAR, xwOBA, xERA, and pitcher arsenal percentile ranks. Metric-agnostic: every view exposes T-1 / T / T+1 / T+2 / T+3 for any trade leg.
- **`ingest/catalog.py`** — frozen-dataclass registry of 24 known stat sources. CLI: `ste catalog [--status ingested|available|blocked] [--source X] [--search Y]`.
- **`storage/teams.py`** — canonical MLB integer team ID ↔ Baseball Reference 3-letter code mapping for the 30 active franchises + 4 historical rebrand aliases (FLA, MON, TBD, ANA).
- **`ingest/stats.py`** — Baseball Reference bWAR adapter (1871-present, 182K player-season-stint rows) + Baseball Savant Statcast adapter (xwOBA / xERA / pitcher percentile ranks, 2015-2024).
- `storage/trade_views.py` — trade-event-level views (`trade_movements`, `trade_events`, `trade_events_affiliated`).
- **`ingest/transactions.py`** — MLB Stats API transactions adapter. 703K rows / 2,734 MLB-affiliated trade events for 1990-2024.
- Initial Phase 1 scaffold: uv project, Python 3.12, ruff + pyright + pytest configured per Rob's conventions; `src/savage_trade_evaluator/` package; DuckDB storage at `data/duckdb/trades.db`; Typer CLI.

### Changed
- Schema bumped to **v3** (was v2). Added `coaches`, `front_office` tables.
- Schema bumped to **v2** (from v1). Added `bwar_batting`, `bwar_pitching`, `statcast_batting_expected`, `statcast_pitching_expected`, `statcast_pitcher_percentile_ranks` tables.
- **`transactions` table primary key** now `(transaction_id, leg_index)` — was `transaction_id` alone, which silently dropped 2nd+ legs of multi-player trades.
- **Insert path**: switched from per-row `conn.execute()` loop to DuckDB pandas-DataFrame registration + `INSERT ... SELECT ... ON CONFLICT`. ~70× speedup measured.
- `BACKTESTER_START_SEASON` extended from 2010 to 1990 (though useful trade data still starts 2010; see D-14).
- Schema initialization now also wires up `teams.initialize()` and `outcome_views.create_all()`.

### Fixed
- BR front-office parser now correctly handles multi-role-per-`<p>` blocks (e.g., LAD 2018 "Manager: Dave Roberts &nbsp; President: Andrew Friedman" in one `<p>`).
- BR front-office parser now strips W-L parenthetical content from manager names ("Dave Roberts (92-71)" → "Dave Roberts").

### Found / decided
- D-09 — D-01 refinement: three valuations per player (current-roster / trade-acquirer / next-FA-acquirer).
- D-10 — Q-03 closed: ATT estimation conditional on pre-trade info; synthetic-control counterfactuals for ex-post training signal.
- D-11 — Q-04 closed: store WAR + components; normalize FV within position-class × era × publication-year.
- D-12 — Q-06 closed: multilevel from day one (Stan / brms / Pyro).
- D-13 — Q-08 closed: posterior distributions mandatory; CRPS / log-score / calibration scoring.
- D-14 — MLB Stats API transaction coverage starts 2010 (pre-2010 essentially empty).
- D-15 — Two-source personnel data (MLB API coaches + BR front-office).
- D-16 — Pressly trade (`transaction_id=371509`) as the V1 canonical validation case.
- D-17 — COVID-2020 baseline distortion for 2021 trades (T-1 WAR suppressed by 60-game season).

### Removed
- (none — V1 has been purely additive)

### Blocked
- FanGraphs (Cloudflare-gated; pybaseball / curl_cffi / cloudscraper all 403). Substituted by bWAR + Statcast.
- Lahman auto-fetch (broken pybaseball zip handling). Substituted by bWAR for all use cases so far.

---

## [0.0.0] — Phase 0 complete (2026-05-15)

Pre-code planning + research. Not tracked in this repo — see `~/.claude/plans/we-re-starting-from-the-smooth-iverson.md` and `~/Vault/savage_vault/wiki/trade-eval--*.md`.

- 22 vault notes: 5 books ingested (MVP Machine, Baseball Between the Numbers, Moneyball synthesis, Statistical Rethinking, Causal Inference: The Mixtape).
- Persona pressure-test captured (six personas: 2 GM archetypes, sabermetrician, coach, player, data scientist).
- 6 of 9 open questions answered (D-01 through D-13 in `trade-eval--decisions.md`).
- Context-aware-valuation thesis established as the spine.
