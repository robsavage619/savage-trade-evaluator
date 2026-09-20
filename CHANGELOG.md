# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions track the V1/V2 milestones from the planning brief.

## [Unreleased]: trust and explainability release (2026-07-05)

### Phase A: housekeeping
- Verified and committed War Room route refactor: `WarRoom.tsx` (−1704 lines) extracted into
  `frontend/src/routes/warroom/` as 11 component files (`AiBrief`, `TradeWorkshop`, `PayrollSection`,
  `RosterShape`, `WindowClock`, `IntelligenceFeed`, `PartnerPanel`, `PostureBanner`, `LeagueTicker`,
  `primitives`, `shared`). Build verified clean (zero TS errors). (`refactor(frontend): extract War Room route into warroom/ modules`)
- Recorded V3.2 baseline backtest metrics in `docs/revalidation/2026-07-baseline.md` (SHA + date header).

### Phase B: non-model bug fixes (D-53, D-54, D-55 partial)
- **D-53** `three_term_value.py`: deduped salary to one row per `(mlb_id, season)` via `MAX()`,
  switched `AVG(salary)` to `SUM(salary)` over the control window. Prior code inflated surplus by roughly a factor of N
  for N-year windows; two-way players had salary double-counted.
- **D-54** `three_term_value.py`: era-aware playoff win curve: pre-2022 midpoint=89, post-2022
  midpoint=86 (12-team expanded playoffs). `evaluate()` threads `trade_season` to Term-3.
- **CLI validation** (`cli.py`): `score-trade` and `suggest-trades` now validate receiver/sender
  bref codes against the `teams` table before feature assembly; an unknown code exits 1 with a valid-codes
  list. Missing org-context row and missing GM profile emit explicit warnings instead of silent
  league-average fallback.
- Investigated the `counterfactuals.py:342` T-1 position lookup and confirmed it is intentional (pre-trade role);
  added clarifying comment.

### Phase C: trust metadata and attribution (D-56)
- **Coverage report** per outcome in `scenario_engine.py`: pre-imputation NaN mask to
  `{n_total, n_observed, n_imputed, imputed_features, observed_fraction, grade}` (A to D). Attached
  to every outcome dict under `"coverage"`.
- **Feature attribution** in `scenario_engine.py`: `attribute_score(fit, features, top_k=5)`.
  `contribution_i = beta_mean_i * x_z_i * y_std`; NaN maps to 0 by construction; top-K with
  observed/imputed + credible flags. Wired to `war_delta` outcome and `score-trade` CLI output.
- `score-trade` CLI prints "WHY THIS SCORE" block: baseline + top-5 contributors + coverage grade
  plus an `extrapolating` warning when the grade is C or D.
- `MODEL_VERSION` literal (`"v3.2"`) replaced with `MODEL_VERSION` import throughout.

### Phase D: model-touching change and revalidation (D-55)
- `v3.py::predict` gains `multiple_imputation: bool = False` API. When enabled, missing features
  receive per-sample draws from N(0,1) clipped to ±5 (z-space) before the noise draw. Complete
  rows are bit-identical to the prior path. (`feat(modeling): predict-time multiple imputation`)
- D-38 revalidation in `docs/revalidation/2026-07-post-mi.md`: **NO-GO**. Marginal MI degraded
  CRPS +14.5% (war_delta) and +16.8% (surplus_wins) on sparse rows due to independent feature draws
  ignoring correlations. `_score_df` reverted to mean-fill. API stays committed for future conditional
  imputation experiment.

### Phase E: product surface (D-56)
- **Typed ScenarioCard**: `frontend/src/data/warroom/types.ts` adds `AttributionItem`, `OutcomeCard`,
  and `ScenarioCard` types; `scenarios: unknown[]` becomes `scenarios: ScenarioCard[]`.
- `scripts/export_warroom.py`: `_trim_scenario()` trims historical scenario dicts to camelCase UI
  fields (war_delta/dollarSurplus/surplusWins means, p5/p95/pPositive, coverage grade +
  observed_fraction, top-3 attribution).
- **Frontend honesty pass**: `computeVerdict` in `hypothetical.ts` gains `method: 'heuristic'`.
  TradeWorkshop and TradeBuilder render a persistent badge: "Heuristic estimate. Uncertainty band is
  a rule of thumb (sqrt(n) * 1.2), not a model posterior." War Room TradeWorkshop renders historical
  ScenarioCards with A-to-D coverage chips (color-coded) and top-3 attribution lines; gated on
  `sc.warDelta != null` for backward compat with old-format JSON.

---

## [Unreleased]: V1 data spine

### Added
- Project Claude config: `CLAUDE.md`, `.claude/settings.json`, slash commands `/check`, `/trade <id>`, `/sources`, `/decisions`.
- `LESSONS.md`, `CHANGELOG.md`, `.claude/SKILLS.md`.
- `ste analyze` CLI surface with three sub-commands:
  - `scope --min-war X`: Q-01 trade-scope-cutoff exploration per season.
  - `dev-fit-jumps --season Y --top N`: pitchers by K-percentile jump from T-1 to T+1.
  - `personnel TRADE_ID`: both-sides front-office and coaches snapshot.
- `analysis/trade_summary.py` module exposing read-only summaries from V1 data.
- `docs/NAIVE_BASELINE.md`: the baseline we want to beat.
- `docs/STATS_CATALOG.md`: human-browsable mirror of the source registry.
- Parser regression tests (5 for BR front-office, 4 for MLB API coaches normalization).
- **`ingest/front_office.py`**: Baseball Reference per-season team-page scraper for GM + President of Baseball Ops + Farm Director + Scouting Director. Rate-limited at 3.5s per request. 1,880 rows for 2010-2024.
- **`ingest/coaches.py`**: MLB Stats API `/teams/{id}/coaches` per team-season. Manager plus bench/hitting/pitching/bullpen/base coaches. 5,408 rows for 2010-2024.
- **`storage/outcome_views.py`** with parallel windows for WAR, xwOBA, xERA, and pitcher arsenal percentile ranks. Metric-agnostic: every view exposes T-1 / T / T+1 / T+2 / T+3 for any trade leg.
- **`ingest/catalog.py`**: frozen-dataclass registry of known stat sources. CLI: `ste catalog [--status ingested|available|blocked] [--source X] [--search Y]`.
- **`storage/teams.py`**: canonical mapping between MLB integer team IDs and Baseball Reference 3-letter codes for the 30 active franchises, plus 4 historical rebrand aliases (FLA, MON, TBD, ANA).
- **`ingest/stats.py`**: Baseball Reference bWAR adapter (1871-present, 182K player-season-stint rows) and Baseball Savant Statcast adapter (xwOBA / xERA / pitcher percentile ranks, 2015-2024).
- `storage/trade_views.py`: trade-event-level views (`trade_movements`, `trade_events`, `trade_events_affiliated`).
- **`ingest/transactions.py`**: MLB Stats API transactions adapter. 703K rows / 2,734 MLB-affiliated trade events for 1990-2024.
- Initial Phase 1 scaffold: uv project, Python 3.12, ruff + pyright + pytest configured per Rob's conventions; `src/savage_trade_evaluator/` package; DuckDB storage at `data/duckdb/trades.db`; Typer CLI.

### Changed
- Schema bumped to **v3** (was v2). Added `coaches`, `front_office` tables.
- Schema bumped to **v2** (from v1). Added `bwar_batting`, `bwar_pitching`, `statcast_batting_expected`, `statcast_pitching_expected`, `statcast_pitcher_percentile_ranks` tables.
- **`transactions` table primary key** is now `(transaction_id, leg_index)`. It was `transaction_id` alone, which silently dropped the 2nd and later legs of multi-player trades.
- **Insert path**: switched from per-row `conn.execute()` loop to DuckDB pandas-DataFrame registration + `INSERT ... SELECT ... ON CONFLICT`. Measured ~70x speedup.
- `BACKTESTER_START_SEASON` extended from 2010 to 1990 (though useful trade data still starts 2010; see D-14).
- Schema initialization now also wires up `teams.initialize()` and `outcome_views.create_all()`.

### Fixed
- BR front-office parser now correctly handles multi-role-per-`<p>` blocks (e.g., LAD 2018 "Manager: Dave Roberts &nbsp; President: Andrew Friedman" in one `<p>`).
- BR front-office parser now strips W-L parenthetical content from manager names ("Dave Roberts (92-71)" becomes "Dave Roberts").

### Found / decided
- D-09: D-01 refinement, three valuations per player (current-roster / trade-acquirer / next-FA-acquirer).
- D-10: Q-03 closed. ATT estimation conditional on pre-trade info; synthetic-control counterfactuals for ex-post training signal.
- D-11: Q-04 closed. Store WAR plus components; normalize FV within position-class, era, and publication-year.
- D-12: Q-06 closed. multilevel from day one (Stan / brms / Pyro).
- D-13: Q-08 closed. posterior distributions mandatory; CRPS / log-score / calibration scoring.
- D-14: MLB Stats API transaction coverage starts 2010 (pre-2010 essentially empty).
- D-15: two-source personnel data (MLB API coaches plus BR front-office).
- D-16: Pressly trade (`transaction_id=371509`) as the V1 canonical validation case.
- D-17: COVID-2020 baseline distortion for 2021 trades (T-1 WAR suppressed by 60-game season).

### Removed
- (none; V1 has been purely additive)

### Blocked
- FanGraphs (Cloudflare-gated; pybaseball / curl_cffi / cloudscraper all 403). Substituted by bWAR plus Statcast at the time. **Unblocked since:** leaderboards and The Board are now ingested through a Firecrawl stealth proxy.
- Lahman auto-fetch (broken pybaseball zip handling). Substituted by bWAR for all use cases so far.

---

## [0.0.0]: Phase 0 complete (2026-05-15)

Pre-code planning and research. Not tracked in this repo; see `~/.claude/plans/we-re-starting-from-the-smooth-iverson.md` and `~/Vault/savage_vault/wiki/trade-eval--*.md`.

- 22 vault notes: 5 books ingested (MVP Machine, Baseball Between the Numbers, Moneyball synthesis, Statistical Rethinking, Causal Inference: The Mixtape).
- Persona pressure-test captured (six personas: 2 GM archetypes, sabermetrician, coach, player, data scientist).
- 6 of 9 open questions answered (D-01 through D-13 in `trade-eval--decisions.md`).
- Context-aware-valuation thesis established as the spine.
