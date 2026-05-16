# savage-trade-evaluator — Claude project context

Rob's global conventions (`~/.claude/CLAUDE.md`) apply. This file is **project-specific overlay**: where the planning lives, what V1 looks like, what's load-bearing, and what to avoid.

---

## Thesis (the spine of everything)

**Context-aware MLB trade valuation.** Same player has *N* valuations, one per acquiring club's contention window, payroll situation, farm depth, positional need, and dev-system fit. Fair value is a tensor, not a scalar. We're explicitly trying to beat the FanGraphs $/WAR style "fair value" naïve baseline.

Refinement (D-09): **three valuations per player at any decision point** — current-roster, trade-acquirer, next-FA-acquirer. Value-capture mismatch means the team developing a player may not be the team capturing his surplus.

## Where to read first

| Document | What it is |
|---|---|
| `~/.claude/plans/we-re-starting-from-the-smooth-iverson.md` | Planning brief — phases, status, open questions, persona pressure-test |
| `~/Vault/savage_vault/wiki/trade-eval--decisions.md` | ADR log (D-01 → D-16). Source of truth for *why* modeling choices were made |
| `~/Vault/savage_vault/wiki/trade-eval--persona-critique-v0.md` | Six personas' V1 critiques (former GMs, sabermetrician, coach, player, data scientist) — every persona's concern maps to a feature we plan to build |
| `~/Vault/savage_vault/wiki/{lindbergh,click-keri,lewis,mcelreath,cunningham}-*.md` | Book ingest notes — MVP Machine, BBtN, Moneyball, Statistical Rethinking, Causal Inference Mixtape |
| `docs/STATS_CATALOG.md` | What stat sources we know about (ingested / available / blocked) |
| `docs/NAIVE_BASELINE.md` | Design of the baseline model we want to beat |

## Phase status (2026-05-15)

- **Phase 0** — research & vault build-up: ✅ done. 22 vault notes, 5 books ingested.
- **Phase 1** — data spine: ✅ V1 substantively complete. 9 commits. 703K transactions, 182K bWAR rows, full Statcast 2015-2024, coaches + front-office personnel.
- **Phase 2** — context-aware valuation model: ☐ next. See `docs/NAIVE_BASELINE.md` for the baseline we're starting from.
- **Phase 3** — GM-behavior layer: ☐ later. Personnel data is ready.
- **Phase 4** — product surface: ☐ later.

## The Pressly canonical case

Ryan Pressly MIN→HOU 2018-07-27 (`trade_event_id=371509`) is the V1 validation reference. The MVP Machine Ch 9 thesis ("the Astros' Brent Strom intake meeting changed Pressly's pitch mix") is **fully encoded in V1 data**:
- bWAR: T-1 = -0.04, T@MIN = 0.73, T@HOU = 1.34, T+1..3 = 1.68 / 0.22 / 1.87
- Arsenal: fb_spin pct 97→98, curve_spin 100→100 (stuff unchanged), K% 65→94, whiff% 69→95 (usage changed)
- Personnel: HOU = Luhnow + Hinch + Strom; MIN = Falvey + Levine + Molitor + Alston

Any V1 model must rate this trade as a clear HOU win. If it doesn't, something is broken before we touch open questions.

## Domain conventions (project-specific)

### Stat sources

- **WAR currency = bWAR** (Baseball Reference). Has full 1871+ history including stints, which we need for trade-year splits.
- **Park-adjusted / regression-baseline stats = Baseball Savant Statcast** (xwOBA, xERA, percentile ranks). 2015+ only but covers the modern dev-fit era.
- **FanGraphs is blocked.** Cloudflare-gated; pybaseball + curl_cffi + cloudscraper all 403. Don't waste cycles trying again — substitutes already in place. The only remaining FG-specific need is prospect FV grades for Phase 2 prospect work, which would require Playwright.
- **Personnel: two sources.** MLB Stats API `/teams/{id}/coaches` for managers + assistants (fast). Baseball Reference per-season team pages for GM + POBO + Farm/Scouting Director (slow scrape).
- **Lahman is broken** (zip-file unzip error in pybaseball). Don't try to use it.

### Backtester scope

- **Trade events: 2010-2024.** MLB Stats API has essentially no trade data pre-2010 (D-14). Pre-2010 history would need Retrosheet (deferred).
- **Player stats: full bWAR coverage 1871+** for aging curves and historical context.
- **Statcast layer: 2015-2024.**

### Modeling

- **Multilevel from day one** (D-12). Team / era / position clusters. Stan / brms / Pyro stack.
- **Outcome metrics are metric-agnostic.** Every "trade_player_*_window" view plugs into the same model interface — WAR, xwOBA, xERA, arsenal percentile ranks are interchangeable outcome variables. Don't hardcode WAR.
- **Outputs are posterior distributions** (D-13), not point estimates. Score with CRPS / log-score / calibration.
- **ATT, not ATE** (D-10). We estimate the average treatment effect on the trades that *happened*; synthetic-control counterfactuals supply the ex-post training signal (Mixtape Ch 10).
- **Three-valuation refinement** (D-09): pre-FA cost-controlled surplus + post-FA open-market surplus + Δ playoff-probability × playoff-revenue.

### Project hygiene

- **Schema version is in `src/savage_trade_evaluator/storage/schemas.py:SCHEMA_VERSION`.** Bump it on additive DDL, drop tables if changing column constraints (no in-place ALTER yet — V1 freezing).
- **DuckDB has an exclusive write lock.** Running `ste ingest <X>` blocks any concurrent read/write. Background ingests + foreground queries = lock conflict. Either serialize or use `read_only=True` after the writer releases.
- **Catalog new sources before wiring them.** Add a `StatSource(...)` entry to `ingest/catalog.py` first; lets us see what's-possible at a glance.

## Things that will save Claude time

- `uv run ste catalog --status ingested` — quickly see what data we have
- `uv run ste status` — DB row counts
- `uv run ste analyze personnel 371509` — Pressly snapshot
- The Pressly case is the "smoke test for everything" — run it after any model change
- If you're tempted to add FanGraphs, **stop.** See above.
- If you're tempted to hand-curate GM data, **stop.** See above — BR scrape works.

## Anti-patterns to avoid

- **Don't claim a model is metric-agnostic** without proving it with a second metric. The arsenal-percentile-rank view exists specifically to keep us honest here.
- **Don't aggregate to WAR before the model layer.** Store components (off / def / runs-above-avg, xwOBA, xERA, arsenal percentiles) and aggregate downstream conditional on receiving-team context.
- **Don't pre-commit to a single outcome window.** Q-02 is testable empirically. Test 3yr + 5yr; pick by predictive separation, not intuition.
- **Don't ignore selection-on-gains.** GMs chose these trades; ATT ≠ ATE. Treat naive comparisons as biased by construction.
