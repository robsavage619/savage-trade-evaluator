# savage-trade-evaluator: agent project context

> **Canonical agent context file.** `AGENTS.md`, `GEMINI.md`, and `.github/copilot-instructions.md` are all symlinks to this file, so edits here propagate to every supported tool (Claude Code, OpenAI Codex / Jules, Gemini CLI, GitHub Copilot, Cursor's AGENTS.md reader, etc.).

Rob's global conventions (`~/.claude/CLAUDE.md`) apply. This file is the **project-specific overlay**: where the planning lives, what V1 looks like, what's load-bearing, and what to avoid.

---

## Thesis (the spine of everything)

**Context-aware MLB trade valuation.** Same player has *N* valuations, one per acquiring club's contention window, payroll situation, farm depth, positional need, and dev-system fit. Fair value is a tensor, not a scalar. We're explicitly trying to beat the FanGraphs $/WAR style "fair value" naïve baseline.

Refinement (D-09): **three valuations per player at any decision point**: current-roster, trade-acquirer, next-FA-acquirer. Value-capture mismatch means the team developing a player may not be the team capturing his surplus.

## Where to read first

| Document | What it is |
|---|---|
| `~/.claude/plans/we-re-starting-from-the-smooth-iverson.md` | Planning brief: phases, status, open questions, persona pressure-test |
| `~/Vault/savage_vault/wiki/trade-eval--decisions.md` | ADR log (D-01 to D-16). Source of truth for *why* modeling choices were made |
| `~/Vault/savage_vault/wiki/trade-eval--persona-critique-v0.md` | Six personas' V1 critiques (former GMs, sabermetrician, coach, player, data scientist). Every persona's concern maps to a feature we plan to build |
| `~/Vault/savage_vault/wiki/{lindbergh,click-keri,lewis,mcelreath,cunningham}-*.md` | Book ingest notes: MVP Machine, BBtN, Moneyball, Statistical Rethinking, Causal Inference Mixtape |
| `docs/STATS_CATALOG.md` | Stat sources, with ingested / available / blocked status and live row counts |
| `docs/NAIVE_BASELINE.md` | Design of the baseline model we want to beat |

## Phase status (2026-05-15)

- **Phase 0**, research and vault build-up: done. 22 vault notes, 5 books ingested.
- **Phase 1**, data spine: done. 832K transaction legs, 184K bWAR rows, full Statcast 2015-2024, coaches and front-office personnel.
- **Phase 2**, context-aware valuation model: done. V3 beats the naive baseline by 28.2% MAE on a 2018-2021 holdout (D-51). Production cache under `data/model_cache/`, keyed by MODEL_VERSION and SCHEMA_VERSION. See `docs/NAIVE_BASELINE.md` for the baseline design and `scripts/benchmark_vs_naive.py` for the GO result.
- **Phase 3**, GM-behavior layer: done. 86 GM behavioral profiles and 5 archetypes (D-52). `gmContext` live in the War Room. The acceptance-probability model is deferred; it needs negative examples.
- **Phase 4**, product surface: done. `ste score-trade`, `ste suggest-trades`, and `scripts/case_studies.py`, all wired to the V3.2 production fit via `assemble_hypothetical` and `score_hypothetical`.

## State addendum (2026-07-05)

- **WarRoom refactor committed**: `frontend/src/routes/WarRoom.tsx` (-1704 lines) extracted into `frontend/src/routes/warroom/` as 11 component files (`AiBrief`, `TradeWorkshop`, `PayrollSection`, `RosterShape`, `WindowClock`, `IntelligenceFeed`, `PartnerPanel`, `PostureBanner`, `LeagueTicker`, `primitives`, `shared`). Build verified clean (zero TS errors) before commit.
- **`.agents/skills/` added, untracked**: 3 skill definitions (`source-command-check`, `source-command-pressly`, `source-command-decisions`).
- Phase-1 commit count above (9) is a snapshot; history has moved on. Trust `git log`, not this file, for counts.

## Validation philosophy

**Diagnose with distributions, not single trades.** The actual diagnostics are:
backtest calibration (90% CI coverage on held-out test set), CRPS / MAE,
and credible-feature counts per outcome (D-26 threshold). A single canonical
trade ("does the model rate Pressly as a HOU win?") is a poor anchor:
hierarchical shrinkage will pull tail-of-distribution outcomes toward the
regime mean by design, and fitting any one outlier tightly is overfitting.
Earlier docs over-indexed on the Pressly case. Don't.

## Domain conventions (project-specific)

### Stat sources

- **WAR currency = bWAR** (Baseball Reference). Has full 1871+ history including stints, which we need for trade-year splits.
- **Park-adjusted / regression-baseline stats = Baseball Savant Statcast** (xwOBA, xERA, percentile ranks). 2015+ only but covers the modern dev-fit era.
- **FanGraphs leaderboards ARE ingested** (2010-2024) via a Firecrawl stealth proxy into `fangraphs_batting_leaders` (20,503 rows) and `fangraphs_pitching_leaders` (11,425 rows), cached under `data/fangraphs_cache/`. The old "blocked" note referred to live pybaseball scraping, which is still true: Cloudflare blocks pybaseball, curl_cffi, and cloudscraper. Don't try pybaseball; the DB tables already have the data. **FanGraphs The Board (prospect FV grades) is also ingested**, 2017-2024, via `scripts/parse_fg_prospects.py` into the `prospect_rankings` table (498 rows) and the `trade_acquired_prospect_fv` view. For forward scoring (2025+) use TJStats instead (MLBAM IDs, no bridging needed).
- **Personnel: two sources.** MLB Stats API `/teams/{id}/coaches` for managers + assistants (fast). Baseball Reference per-season team pages for GM + POBO + Farm/Scouting Director (slow scrape).
- **Lahman is broken** (zip-file unzip error in pybaseball). Don't try to use it.

### Backtester scope

- **Trade events: 2010-2024.** MLB Stats API has essentially no trade data pre-2010 (D-14). Pre-2010 history would need Retrosheet (deferred).
- **Player stats: full bWAR coverage 1871+** for aging curves and historical context.
- **Statcast layer: 2015-2024.**

### Modeling

- **Multilevel from day one** (D-12). Team / era / position clusters. Stan / brms / Pyro stack.
- **Outcome metrics are metric-agnostic.** Every "trade_player_*_window" view plugs into the same model interface. WAR, xwOBA, xERA, and arsenal percentile ranks are interchangeable outcome variables. Don't hardcode WAR.
- **Outputs are posterior distributions** (D-13), not point estimates. Score with CRPS / log-score / calibration.
- **ATT, not ATE** (D-10). We estimate the average treatment effect on the trades that *happened*; synthetic-control counterfactuals supply the ex-post training signal (Mixtape Ch 10).
- **Three-valuation refinement** (D-09): pre-FA cost-controlled surplus, plus post-FA open-market surplus, plus change in playoff probability times playoff revenue.

### Project hygiene

- **Schema version is in `src/savage_trade_evaluator/storage/schemas.py:SCHEMA_VERSION`.** Bump it on additive DDL, drop tables if changing column constraints (no in-place ALTER yet; V1 is frozen). Currently at v39.
- **DuckDB has an exclusive write lock.** Running `ste ingest <X>` blocks any concurrent read/write. Background ingests + foreground queries = lock conflict. Either serialize or use `read_only=True` after the writer releases.
- **Catalog new sources before wiring them.** Add a `StatSource(...)` entry to `ingest/catalog.py` first; lets us see what's-possible at a glance.

## Things that will save Claude time

- `uv run ste catalog --status ingested`: see what data we have
- `uv run ste status`: DB row counts
- `uv run python scripts/v2_full_backtest.py`: the real smoke test (calibration plus credible-feature counts across all 4 outcomes)
- If you're tempted to add FanGraphs, **stop.** See above.
- If you're tempted to hand-curate GM data, **stop.** See above. The BR scrape works.

## Anti-patterns to avoid

- **Don't claim the model is metric-agnostic** without proving it with a second metric. The arsenal-percentile-rank view exists specifically to keep us honest here.
- **Don't aggregate to WAR before the model layer.** Store components (off / def / runs-above-avg, xwOBA, xERA, arsenal percentiles) and aggregate downstream conditional on receiving-team context.
- **Don't pre-commit to a single outcome window.** Q-02 is testable empirically. Test 3yr + 5yr; pick by predictive separation, not intuition.
- **Don't ignore selection-on-gains.** GMs chose these trades, so ATT is not ATE. Treat naive comparisons as biased by construction.
