<p align="center">
  <img src="banner.svg" alt="Savage Analytics — Context-aware MLB trade valuation" width="100%"/>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12-blue.svg" alt="python 3.12"/></a>
  <a href="https://docs.astral.sh/ruff/"><img src="https://img.shields.io/badge/code%20style-ruff-261230" alt="ruff"/></a>
  <a href="https://microsoft.github.io/pyright/"><img src="https://img.shields.io/badge/type%20check-pyright-blue" alt="pyright"/></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/badge/packaging-uv-de5fe9" alt="uv"/></a>
  <a href="https://duckdb.org/"><img src="https://img.shields.io/badge/store-DuckDB-fff100" alt="DuckDB"/></a>
  <a href="frontend/"><img src="https://img.shields.io/badge/frontend-React%2019-61dafb" alt="React 19"/></a>
  <a href="frontend/"><img src="https://img.shields.io/badge/build-Vite%208-646cff" alt="Vite 8"/></a>
</p>
<p align="center">
  <a href="RESEARCH_LOG.md"><img src="https://img.shields.io/badge/research_rounds-35-success" alt="rounds completed"/></a>
  <a href="https://github.com/robsavage619/savage-trade-evaluator"><img src="https://img.shields.io/badge/ADR_decisions-30-success" alt="decisions logged"/></a>
  <a href="src/savage_trade_evaluator/storage/schemas.py"><img src="https://img.shields.io/badge/duckdb_schema-v20-informational" alt="schema"/></a>
  <a href="docs/DATA_SOURCE_PROBE.md"><img src="https://img.shields.io/badge/duckdb_rows-1.29M-informational" alt="rows"/></a>
</p>

---

## What this is

**Savage Analytics** is a full-stack research platform for evaluating MLB trades. The backend is a research-grade data spine + Bayesian analytical framework. The frontend is a React SPA with 7 routes covering org scouting, player profiling, trade construction, and live research findings.

The core claim: **same player, different teams, different valuations.** Not a Sabermetric calculator. Not another $/WAR chart. A claims-and-receipts engine for the question *"was this trade a good move for this specific team in this specific era under this specific GM?"*

The project began with one specific thesis: **the Dodgers' MLB-leading dev system inflates prospects who then fail elsewhere.** 35 rounds of testing later, the thesis is empirically rejected — but the *process* of rejecting it produced a richer framework, the project's most-supported single finding (TEX-Daniels sell-high), the largest credible coefficient in the program (pitcher K%-trajectory at -10.8 K-percentile-points), and a 2D org-quality map that replaces the system-tax narrative entirely.

**The single most useful artifact:** the 2D `(dev WAR, trade Δ)` coordinate map of all 30 franchises. See [Headline findings](#headline-findings) below.

---

## TL;DR — what we found

After **35 research rounds** and **30 logged decisions**:

### Original thesis: rejected

The "Dodgers system-tax" thesis predicted young system-developed prospects should regress after being traded out of LAD. They don't. Across all 16 regimes tested in [R-30](RESEARCH_LOG.md), the YOUNG-PROSPECT bucket is *positive* in every single one. Young players who get traded gain WAR after, regardless of which org they leave. Confidence: high. Receipts: [`scripts/sell_high_vs_system_tax.py`](scripts/sell_high_vs_system_tax.py).

### The three confirmed-by-data findings

| Finding | Magnitude | Confidence | Receipts |
|---|---|---|---|
| **TEX-Jon Daniels' sell-high skill** | 9 vets traded, mean Δ -2.54 WAR (Lucroy, Minor, Michael Young, Darvish, Chirinos…). Survives trimming. | Credible at conventional thresholds. The cleanest specific-person finding in the project. | [R-29/30](RESEARCH_LOG.md) |
| **Pitcher K%-trajectory predicts post-trade decline** | Coefficient = -10.8 K-percentile-points per +1 SD pre-trade trajectory. 90% CI [-17.1, -4.3]. **Mass = 100%.** | Strongest predictive finding in the project. Visible only with K% as outcome. | [R-22](RESEARCH_LOG.md) |
| **Three rate-based-outcome features** | On xwOBA-delta outcome: experience -99%, war_trajectory -98%, player_quality +96% mass. First credibly-real coefficients in 19 rounds of ablations. | Real but at small n (143 rows). | [R-19](RESEARCH_LOG.md) |

### Five methodology corrections (in narrative order)

| Correction | Lesson | Decision |
|---|---|---|
| **Architectural** | Within-team-variation features beat static team features in multilevel-w/-team-cluster models. | [D-24](https://github.com/robsavage619/savage-trade-evaluator) |
| **Metric** | Rate-based outcomes (xwOBA, K%, era_plus) surface signal that WAR outcomes hide. Default away from WAR for research. | [D-25, D-26](https://github.com/robsavage619/savage-trade-evaluator) |
| **Regime** | GM identity drives ~3× more variance than team identity. Cluster on (team, regime), not team. | [D-28](https://github.com/robsavage619/savage-trade-evaluator) |
| **Mechanism** | Sell-high ≠ system-tax. Per-regime negative intercepts must be decomposed into vet-at-peak vs young-prospect buckets. | [D-29](https://github.com/robsavage619/savage-trade-evaluator) |
| **Coverage** | Dev credit ≠ trade Δ. Teams should get credit for developing players who become stars elsewhere. | D-30 candidate |

### The R-33/34/35 arc — V3 model adoption

Three sequential bracket tests ([R-33](RESEARCH_LOG.md), [R-34](RESEARCH_LOG.md), [R-35](RESEARCH_LOG.md)) compared V0 (no pooling) / V1 (team-cluster) / V2 (team+regime nesting) on identical data. **Team pooling and regime nesting both add zero predictive signal over a flat population-level intercept.** The multilevel structure that motivated V2 was discarded. The active model is now V3 — single-level Bayesian regression with per-outcome feature selection.

**Full synthesis:** [`docs/PHASE1_SYNTHESIS.md`](docs/PHASE1_SYNTHESIS.md).

---

## Headline findings

### The 2D Org-Quality Map

Every franchise gets a `(dev WAR, trade Δ)` coordinate. **The two axes are roughly orthogonal** — being good at dev doesn't predict being good at trading.

```
                    trade Δ (mean post-trade Δ WAR of departed players)
                                       +0.10
                                         |
                                STL  ←   |   ← HOU  (UNIQUE HIGH-DEV/POS-TRADE)
                                         |   ← ARI
              LOW-DEV / POS-TRADE        |        HIGH-DEV / POS-TRADE
                                         |
                                         |
                                ─────────+─────────── dev WAR (median 1200)
                                         |
                                         |
              LOW-DEV / NEG-TRADE        |        HIGH-DEV / NEG-TRADE
                                         |
                                         |
                                TBR  ←   |   ← OAK   (-0.26)
                                SFG  ←   |   ← CHW   (-0.34)
                                         -0.37
```

### Top dev pipelines (1990+ debutees, current 30 franchises only)

| Rank | Team | Dev WAR | Intl WAR | Total | Trade Δ | Quadrant |
|---|---|---|---|---|---|---|
| 1 | CLE | 1353 | 401 | **1754** | -0.14 | HIGH-DEV / ABOVE-MEDIAN |
| 2 | NYY | 1109 | 423 | 1532 | -0.07 | HIGH-DEV / ABOVE-MEDIAN |
| **3** | **HOU** | **1224** | **304** | **1528** | **+0.05** | **HIGH-DEV / POS-TRADE — UNIQUE** |
| 4 | LAD | 1198 | 310 | 1508 | -0.03 | HIGH-DEV / ABOVE-MEDIAN |
| 5 | SEA | 1123 | 376 | 1499 | -0.19 | HIGH-DEV / BELOW-MEDIAN |
| **16** | **STL** | **1102** | **98** | **1200** | **+0.10** | **LOW-DEV / STRONG-POS-TRADE — UNIQUE** |
| 25 | TBR | 776 | 104 | 880 | -0.37 | LOW-DEV / WORST trade Δ |
| 29 | SDP | 691 | 118 | 809 | -0.24 | bottom quadrant |
| **30** | **SFG** | **624** | **48** | **671** | **-0.35** | **dead last on both axes** |

Full table: [`docs/PHASE1_SYNTHESIS.md#the-2d-org-quality-map`](docs/PHASE1_SYNTHESIS.md). Reproducible from [`scripts/dev_credit_full.py`](scripts/dev_credit_full.py).

### What this means in plain English

- **HOU is in a class of its own** — the only HIGH-DEV / TRULY-POSITIVE-TRADE org in baseball.
- **STL is the trade-skill leader** — the "Cardinal Way" is real but it's about trading, not their farm.
- **CLE has the deepest dev pipeline** (1754 total WAR including international).
- **NYY's international scouting is #1** (423 WAR), undercutting the "buy stars" stereotype.
- **The Dodgers are not anomalous** — top-tier on both axes but not exceptional on either. The system-tax reputation is overstated.
- **SFG and SDP are bottom-quadrant.** SFG's 2010-2014 World Series runs look like outliers relative to underlying franchise quality.

---

## Quick start

```bash
# Install (uv handles Python 3.12 + every dep)
uv sync

# Initialize schema (DuckDB v20 + teams + views)
uv run ste init

# Ingest the V1 data spine
uv run ste ingest transactions               # MLB Stats API trades 2010-2024 (~30s)
uv run ste ingest retrosheet-transactions    # Retrosheet trades 1990-2009 (~30s, 17K legs)
uv run ste ingest bwar                       # Baseball Reference WAR, all-time (~10s)
uv run ste ingest statcast                   # Baseball Savant 2015-2024 (~10s)
uv run ste ingest statcast-extended          # Batter percentiles + pitcher arsenal + OAA (~5min)
uv run ste ingest draft                      # MLB Stats API draft 1990-2024 (~30s, 46K picks)
uv run ste ingest coaches                    # MLB API coaching staff per team-season (~3min)
uv run ste ingest front-office --start 1990  # BR front-office 1990-2024 (~50min, rate-limited)
uv run ste ingest chadwick                   # Chadwick register (birth dates + IDs)  ~5s
uv run ste ingest mlb-people                 # Per-player MLB profiles (country/handedness)  ~30s
uv run ste ingest awards                     # MVP/CY/ROY/etc 1990-2024  ~2min
uv run ste ingest catcher-framing            # Statcast catcher framing 2015-2024  ~5s
uv run ste ingest game-logs                  # Retrosheet per-game data 1990-2024  ~1min
uv run ste ingest parks                      # Retrosheet park reference  ~1s
uv run ste ingest pitch-movement             # Statcast pitch physics 2015-2024  ~5min
uv run ste ingest rosters                    # 40-man rosters per team-season  ~5min
uv run ste ingest venues                     # MLB venues with dimensions  ~1s
uv run ste ingest team-season-stats          # Per-team-season aggregates  ~3min
uv run ste ingest spotrac                    # Spotrac contracts (17K, $49B)  ~5min

# Check what landed
uv run ste status
uv run ste catalog --status ingested
```

### Quick reads

```bash
# Pressly trade — V1 personnel reconstruction (MIN→HOU 2018-07-27)
uv run ste analyze personnel 371509

# Run the headline 2D org-quality map
uv run python scripts/dev_credit_full.py

# Run R-22 pitcher K%-trajectory ablation (the largest credible coefficient)
uv run python scripts/ablation_multi_outcome_omnibus.py

# Re-derive the TEX-Daniels sell-high finding
uv run python scripts/sell_high_vs_system_tax.py

# Generate an HTML research report
uv run python -m savage_trade_evaluator.reports.builder

# Browse known stat sources
uv run ste catalog                            # all entries
uv run ste catalog --status ingested          # what's loaded
uv run ste catalog --status blocked           # FanGraphs etc.
```

---

## Data layer at a glance

**29 tables · 1.29M rows · schema v20**

| Source | Coverage | Rows | Notes |
|---|---|---|---|
| **MLB Stats API transactions** | 2010-2024 | 703K | Comprehensive 2010+; sparse pre-2010 (D-14) |
| **Retrosheet transactions** | 1880-2009 | 16,890 trade legs | Fills the pre-2010 gap (D-22 ID-offset) |
| **bWAR batting + pitching** | 1871+ | 182K player-seasons | The all-era spine |
| **Statcast batting expected** | 2015+ | 8,500 | xwOBA, xBA, xSLG |
| **Statcast pitching expected** | 2015+ | 8,095 | xERA, xwOBA-against |
| **Statcast pitcher percentile ranks** | 2015+ | 6,809 | K%, whiff%, FB velocity, spin |
| **Statcast batter percentile ranks** | 2015-2024 | 6,460 | Chase%, hard-hit%, sprint speed, OAA, bat speed |
| **Statcast pitcher arsenal stats** | 2015-2024 | 13,542 | Per-pitch-type breakdowns |
| **Statcast pitch movement** | 2015-2024 | 17,553 | Per-pitcher per-pitch-type physics (velocity, break, percentiles) |
| **Statcast catcher framing** | 2015-2024 | 580 | Per-catcher framing runs by zone |
| **Statcast Outs Above Average** | 2015-2024 | 2,479 | Defensive metric across 5 positions |
| **Draft picks (MLB Stats API)** | 1990-2024 | 46,127 | Round, pick number, signing bonus, scouting report |
| **Chadwick Register** | all-time | 127,526 | Birth dates + ID cross-walks (MLBAM↔Retro↔BRef↔FG) |
| **MLB Stats API people** | all-time | 23,617 | Birth country, bat/pitch hand, height/weight, debut date |
| **MLB awards** | 1990-2024 | 1,733 | MVP/CY/ROY/GG/SS/HOF recipients (17 award types) |
| **Retrosheet game logs** | 1990-2024 | 80,798 | Per-game date, teams, scores, park, attendance |
| **Retrosheet parks** | all-time | 260 | Park metadata (name, city, dates, league) |
| **MLB venues** | all | 1,646 | Capacity, dimensions, surface, roof |
| **Team rosters (40-man)** | 2010-2024 | 22,549 | Per team-season player composition |
| **Team season stats** | 2010-2024 | 1,350 | Per-team-season hitting/pitching/fielding aggregates |
| **MLB coaches** | 2010-2024 | 5,380 | Manager + assistants per team-season |
| **BR front-office personnel** | 1990-2024 | 2,000+ | GM, POBO, Farm Director, Scouting Director |
| **MLB standings** | 1990-2024 | ~450 | Wins, losses, win pct |
| **Spotrac contracts** | 2000-2024 | ~17,000 | $49B total value; empirical $/WAR curve replacing hardcoded |
| **MiLB stats** | recent | — | Minor league quality features for V3 model |
| **TJStats (Nestico API)** | 2015+ | — | Public API (tjstats.ca); mapped in catalog |

**Storage:** DuckDB single-file at `data/duckdb/trades.db`. Schema version 20. Versioned DDL at [`src/savage_trade_evaluator/storage/schemas.py`](src/savage_trade_evaluator/storage/schemas.py).

**What we don't have:** FanGraphs (Cloudflare-blocked, D-25), MLB Pipeline top-100 prospect lists (lazy-load JS, deferred to Playwright), comprehensive international amateur signing data (proxied via post-1995-not-in-draft-picks; real ingest deferred).

---

## The Pressly trade — canonical V1 validation

The Ryan Pressly trade (MIN → HOU, 2018-07-27, `trade_event_id=371509`) is the V1 smoke-test. The MVP Machine Ch 9 thesis — that the Astros' Brent Strom intake meeting changed Pressly's pitch mix and turned him into an All-Star reliever — is **fully reconstructable from V1 data**:

| Window | bWAR | xwOBA | K% pct | whiff% pct | fb_spin pct | curve_spin pct |
|---|---|---|---|---|---|---|
| T-1 (MIN 2017) | -0.04 | — | 65 | 69 | 97 | 100 |
| T (split 2018) | 0.73 / 1.34 | — | — | — | — | — |
| T+1 (HOU 2019) | 1.68 | — | **94** | **95** | 98 | 100 |
| T+2 (HOU 2020) | 0.22 | — | — | — | — | — |
| T+3 (HOU 2021) | 1.87 | — | — | — | — | — |

**Read:** *stuff* (fb_spin, curve_spin) barely changed; *outcomes* (K%, whiff%) jumped from 65th/69th percentile to 94th/95th. The Astros didn't fix Pressly's mechanics — they fixed his pitch *usage*. Exactly the Ch 9 thesis.

Personnel triangle was also fully reconstructed: HOU = Luhnow/Hinch/Strom; MIN = Falvey/Levine/Molitor/Alston. See `uv run ste analyze personnel 371509`.

Note: Pressly is a strong reconstruction case, but not a reliable model calibration anchor — hierarchical shrinkage pulls tail-of-distribution outcomes toward the regime mean by design (see validation philosophy in [CLAUDE.md](CLAUDE.md)).

---

## Architecture

```
savage-analytics/
├── README.md                              ← you are here
├── docs/
│   ├── PHASE1_SYNTHESIS.md                ← the project's "where we are" doc, read first
│   ├── STATS_CATALOG.md                   ← registry of stat sources, ingested + available + blocked
│   ├── NAIVE_BASELINE.md                  ← the baseline model we want to beat
│   └── V2_DESIGN.md                       ← archived; V3 single-level model supersedes this
├── RESEARCH_LOG.md                        ← R-01 → R-35 chronological experiment log
├── LESSONS.md                             ← gotchas, perf wins, hard-earned lessons
├── CHANGELOG.md                           ← Keep-a-Changelog format
├── CLAUDE.md / AGENTS.md / GEMINI.md      ← agent-context files (symlinked to CLAUDE.md)
│
├── frontend/                              ← Savage Analytics React SPA
│   ├── src/
│   │   ├── routes/                        ← 7 route components
│   │   │   ├── OrgExplorer.tsx            # org comparison / 2D map
│   │   │   ├── OrgScout.tsx               # deep org-level analysis
│   │   │   ├── PlayerProfile.tsx          # player detail + percentile radar
│   │   │   ├── PresslyCase.tsx            # canonical V1 validation case
│   │   │   ├── Research.tsx               # scroll-driven research findings
│   │   │   ├── TradeBuilder.tsx           # trade evaluation interface
│   │   │   └── TradeWorkspace.tsx         # multi-trade workspace
│   │   ├── components/                    ← shared UI components
│   │   │   ├── AiReasoning.tsx            # AI reasoning drawer
│   │   │   ├── ClaudeCodeDrawer.tsx       # Claude Code dev integration
│   │   │   ├── FarmSystem.tsx             # farm / prospect visualization
│   │   │   ├── PercentileRadar.tsx        # Statcast percentile radar charts
│   │   │   ├── PersonnelTriangle.tsx      # GM / manager / coach triangle
│   │   │   ├── PosteriorViolin.tsx        # Bayesian posterior violin plots
│   │   │   ├── TeamIdentitySwitcher.tsx   # acquiring-team context switcher
│   │   │   ├── TradePipeline.tsx          # trade leg visualization
│   │   │   └── ...                        # PlayerCard, Sparkline, TeamLogo, etc.
│   │   ├── data/                          ← seed data (orgs, farm, player index)
│   │   └── types.ts
│   └── package.json                       ← React 19, Vite 8, Tailwind 4, TS 6
│
├── src/savage_trade_evaluator/
│   ├── config.py                          # paths, settings, logging
│   ├── cli.py                             # typer CLI (`ste <verb>`)
│   ├── ingest/
│   │   ├── transactions.py                # MLB Stats API trades
│   │   ├── retrosheet_transactions.py     # Retrosheet pre-2010 fill (D-22)
│   │   ├── stats.py                       # bWAR + Statcast expected stats
│   │   ├── statcast_extended.py           # batter pct ranks + pitcher arsenal + OAA
│   │   ├── coaches.py                     # MLB API coaching staff
│   │   ├── front_office.py                # BR front-office scrape
│   │   ├── draft.py                       # MLB Stats API draft endpoint
│   │   ├── standings.py                   # final standings per season
│   │   ├── spotrac.py                     # Spotrac contracts (17K rows, $49B)
│   │   ├── milb_stats.py                  # MiLB stats (minor league quality features)
│   │   ├── prospects.py                   # prospect ingest
│   │   ├── fortification.py               # fortification-pass sources
│   │   └── catalog.py                     # stat-source registry
│   ├── storage/
│   │   ├── db.py                          # DuckDB connection context manager
│   │   ├── schemas.py                     # versioned DDL (current v20)
│   │   ├── teams.py                       # MLB↔bWAR↔Retrosheet team-code mapping
│   │   ├── trade_views.py                 # trade_movements, trade_events, etc.
│   │   └── outcome_views.py               # metric-agnostic outcome-window views
│   ├── modeling/
│   │   ├── naive_baseline.py              # FanGraphs-style $/WAR baseline (to beat)
│   │   ├── v3.py                          # V3 single-level Bayesian regression (active)
│   │   ├── v2/                            # V2 multilevel (archived; superseded by V3)
│   │   ├── bayesian.py                    # PyMC fitting + CRPS scoring
│   │   └── features.py                    # team-season feature engineering
│   ├── reports/                           # HTML report generation
│   │   ├── builder.py                     # report assembly
│   │   └── charts.py                      # Plotly chart helpers
│   └── analysis/
│       ├── trade_summary.py               # read-only trade lookups
│       └── backtest.py                    # out-of-time backtest harness
│
├── scripts/                               # 20+ standalone reproducible analyses
│   ├── ablation_*.py                      # R-06 through R-22 feature ablations
│   ├── origin_org_*.py                    # R-10 through R-22 origin-org tests
│   ├── regime_control_reruns.py           # R-27 (team, regime) clustering
│   ├── all_regimes_ranked.py              # R-28 full 66-regime ranking
│   ├── investigate_regime_anomalies.py    # R-29 archaeology
│   ├── sell_high_vs_system_tax.py         # R-30 mechanism decomposition
│   ├── dev_credit_full.py                 # R-31 dev-credit + 2D map
│   ├── org_stability_decade_split.py      # R-25 variance decomposition
│   ├── export_farm.py                     # export farm system seed data
│   ├── export_org_profiles.py             # export org profile JSON
│   ├── export_player_index.py             # export player index for frontend
│   ├── export_player_profiles.py          # export per-player JSON for frontend
│   └── export_seed.py                     # full frontend seed export
│
├── tests/                                 # unit tests for parsers, schema, IDs
└── data/
    ├── duckdb/trades.db                   # the single-file store
    └── static/retrosheet/tranDB.zip       # Retrosheet cached download
```

---

## Frontend — Savage Analytics SPA

The [`frontend/`](frontend/) directory is a production React application. It runs independently of the Python backend — the frontend consumes exported JSON seed data (generated by `scripts/export_*.py`) rather than hitting a live API.

**Tech stack:**

| | |
|---|---|
| Framework | React 19.2.6 + React Router 7.15.1 |
| Build | Vite 8.0.12 |
| Styling | Tailwind CSS 4.3.0 |
| State | Zustand 5.0.13 |
| Animation | Framer Motion 12.38.0 |
| Charts | Recharts 3.8.1 |
| Data viz | d3-array, d3-scale |
| Types | TypeScript 6.0.2 |
| Icons | Lucide React |

**Routes:**

| Route | Component | What it does |
|---|---|---|
| `/` | OrgExplorer | 2D org-quality map; all 30 franchises at a glance |
| `/org/:team` | OrgScout | Deep org analysis — dev pipeline, trade history, regime breakdown |
| `/player/:id` | PlayerProfile | Player detail with Statcast percentile radar and posterior violin plots |
| `/pressly` | PresslyCase | Interactive reconstruction of the MIN→HOU 2018 canonical trade |
| `/research` | Research | Scroll-driven findings page wired to R-NN summaries |
| `/trade` | TradeBuilder | Trade evaluation interface with context switching |
| `/workspace` | TradeWorkspace | Multi-trade workspace for side-by-side comparisons |

**Running the frontend:**

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173

# Type check + build
npm run build
```

**Regenerate frontend seed data from the DB:**

```bash
uv run python scripts/export_seed.py          # full export (orgs + players)
uv run python scripts/export_player_profiles.py
uv run python scripts/export_org_profiles.py
uv run python scripts/export_farm.py
```

---

## Modeling — V3 single-level Bayesian

The active model is **V3** ([`src/savage_trade_evaluator/modeling/v3.py`](src/savage_trade_evaluator/modeling/v3.py)).

### Why V3 replaced V2

R-33, R-34, and R-35 ran a V0/V1/V2 bracket on identical data:
- **V0** — no pooling, flat population-level intercept
- **V1** — team-cluster random intercepts
- **V2** — (team, GM-regime) nested random intercepts

Result: V1 and V2 add zero predictive signal over V0. The multilevel structure that motivated V2 was producing more complex priors with no CRPS benefit. V3 is V0 with per-outcome feature selection.

### V3 key properties

- **Single-level Bayesian regression** (PyMC), one model per outcome metric
- **Outcome window:** war_delta uses T+2…T+5 (skips T+1 transition year; ~30% MAE improvement — Q-07)
- **Per-outcome feature selection** (D-27): features are selected per metric, not shared across outcomes
- **Contention-window feature** live (Q-01/Q-02): acquirer's playoff probability at trade date
- **Empirical $/WAR curve** from Spotrac veterans (17K contracts, $49B) replaces hardcoded market rate
- **Credibility threshold:** 90% CI excludes zero AND directional mass ≥ 95%

### V3 CLI

```bash
uv run ste v2 fit          # fit the model (note: v2 CLI namespace, V3 architecture)
uv run ste v2 backtest     # out-of-time backtest
uv run ste v2 predict      # score a specific trade
```

V2's multilevel design is documented in [`docs/V2_DESIGN.md`](docs/V2_DESIGN.md) for reference; it is not the active architecture.

---

## How to read this repo

If you have **15 minutes:**
1. [`docs/PHASE1_SYNTHESIS.md`](docs/PHASE1_SYNTHESIS.md) — the full narrative arc with findings, confirmations, rejections, and Phase 2 lessons

If you have **30 minutes:**
2. This README (you're here)
3. [`RESEARCH_LOG.md`](RESEARCH_LOG.md) — pick the R-NN entries that interest you. R-19, R-22, R-25, R-30, R-31, R-33/34/35 are the highlight reel
4. [`~/Vault/savage_vault/wiki/trade-eval--decisions.md`](https://github.com/robsavage619/savage-trade-evaluator) — 30 modeling/scope decisions in ADR format

If you have **an afternoon:**
5. Pick a `scripts/*.py` file, read the docstring, run it, inspect the output
6. Read [`docs/STATS_CATALOG.md`](docs/STATS_CATALOG.md) — the registry of every data source we know about, with ingest/available/blocked status
7. Spin up the frontend: `cd frontend && npm run dev`

If you have **a weekend:**
8. Stand up your own ingest pipeline. The CLI is documented; the schema is in [`schemas.py`](src/savage_trade_evaluator/storage/schemas.py). Try beating the [`docs/NAIVE_BASELINE.md`](docs/NAIVE_BASELINE.md) baseline.

---

## The seven Phase 2 lessons (codified)

The 35-round arc produced seven methodology principles that any future work on this project should treat as load-bearing:

1. **Default to rate-based outcomes** (xwOBA, K%, xERA, era_plus) for any research-thread test. WAR is preserved only for the surplus-value baseline (product convention). [D-26](https://github.com/robsavage619/savage-trade-evaluator)

2. **Cluster on (team, GM-regime), not just team** in any model that spans multiple decades. 90% of within-franchise variance is regime-driven. [D-28](https://github.com/robsavage619/savage-trade-evaluator)

3. **Within-team-variation features beat static team features** in multilevel models with team-cluster random intercepts. [D-24](https://github.com/robsavage619/savage-trade-evaluator)

4. **Credibility threshold = 90% CI excludes zero AND directional mass ≥ 95%**, not CRPS movement. Test-set CRPS is unreliable below n=100.

5. **Per-regime claims must replicate across 2+ outcome metrics** to count as confirmed. [D-25](https://github.com/robsavage619/savage-trade-evaluator)

6. **Per-regime intercepts must be decomposed into sell-high vs system-tax buckets** to interpret the mechanism. [D-29](https://github.com/robsavage619/savage-trade-evaluator)

7. **Multilevel structure is not free.** R-33/34/35 proved team pooling and regime nesting add zero signal in this dataset. Start flat (V3); only add hierarchy if it earns its complexity.

---

## Open follow-ups (deferred to Phase 2+)

- [ ] Build a **sell-high detection feature** for V3 based on TEX-Daniels' archetype
- [ ] **Re-ablate the 5 WAR-null features** (R-06/07/09/14) against rate-based outcomes — several may surface
- [ ] **Scrape MLB Trade Rumors / Baseball America** international signing trackers via Playwright (no public API)
- [ ] **Rate-based-surplus naive baseline** (xwoba_received − xwoba_given_up) as the V3 model target
- [ ] **Cross-metric replicate R-22's k_trajectory** under V3 single-level architecture
- [ ] **Per-pitch-type dev-fit analysis** using `statcast_pitcher_arsenal_stats`
- [ ] **fWAR cross-check** on the project's main findings (currently bWAR-only per D-11)
- [ ] **MLB Pipeline top-100** ingest via Playwright (lazy-loaded JS)
- [ ] **Extend contention window feature** (Q-02) across all outcome metrics

---

## Reading library

The project's analytical framework is shaped by a specific set of books, ingested into the vault and referenced throughout the research log. Read at least the first two if you want to follow the technical thread:

1. **Lindbergh & Sawchik, *The MVP Machine* (2019)** — the modern dev-fit thesis (Ch 9 = the Pressly case)
2. **Click & Keri, *Baseball Between the Numbers* (2006)** — the canonical sabermetric reference. Ch 5-2 on $/WAR currency, Ch 9-3 on log-5 playoff probability
3. McElreath, *Statistical Rethinking* (2nd ed., 2020) — multilevel Bayesian methodology backing every R-NN ablation
4. Cunningham, *Causal Inference: The Mixtape* (2021) — Ch 10 synthetic control framework (queued for V2+)
5. Longenhagen & McDaniel, *Future Value* (2020) — FV-grade-to-WAR mapping (R-08-prep)

Plus, importantly:

- **Pinheiro & Szymanski (2022) "On the Efficiency of Trading Intangible Fixed Assets in Major League Baseball"** ([SSRN 4305663](https://ssrn.com/abstract=4305663)) — mean-variance portfolio framing applied to MLB trades. Validates D-26 metric-correction direction.

Notes at `~/Vault/savage_vault/wiki/{lindbergh,click-keri,lewis,mcelreath,cunningham,longenhagen-mcdaniel}-*.md`.

---

## Agent context files (cross-tool)

The repo root has a fan of agent-context files. All are symlinks to **[`CLAUDE.md`](CLAUDE.md)** — single source of truth. Edit `CLAUDE.md` and every consumer sees the change.

| File | Read by |
|---|---|
| `CLAUDE.md` | **Canonical.** Claude Code; also where humans look. |
| `AGENTS.md` | OpenAI Codex / Jules, Cursor, agents.md standard tools |
| `GEMINI.md` | Google Gemini CLI |
| `.github/copilot-instructions.md` | GitHub Copilot |

Project meta docs:

- [`SKILLS.md`](SKILLS.md) — project-specific skill routing
- [`LESSONS.md`](LESSONS.md) — gotchas + perf wins
- [`RESEARCH_LOG.md`](RESEARCH_LOG.md) — full R-NN experiment record
- [`CHANGELOG.md`](CHANGELOG.md) — Keep-a-Changelog format
- [`docs/PHASE1_SYNTHESIS.md`](docs/PHASE1_SYNTHESIS.md) — the synthesis doc

---

## Dev

```bash
# Backend — lint + format
uv run ruff check src/ scripts/ tests/
uv run ruff format src/ scripts/ tests/

# Backend — type check
uv run pyright src/

# Backend — tests
uv run pytest

# Frontend — dev server
cd frontend && npm run dev

# Frontend — type check + build
cd frontend && npm run build

# Frontend — lint
cd frontend && npm run lint

# Reproduce any R-NN: pick a script, read its docstring, run it
uv run python scripts/<analysis>.py
```

**Pre-commit:** ruff + pyright on changed files. **CI:** none yet (it's a research repo).

---

## Project conventions (Rob's stack — non-negotiable)

| | |
|---|---|
| Language | Python 3.12 |
| Lint/format | `ruff` (not black, not flake8) |
| Type | `pyright` (basic mode) |
| Packages | `uv` (not pip, not poetry) |
| Config | `pyproject.toml` only |
| Layout | `src/savage_trade_evaluator/` |
| Code style | `from __future__ import annotations`, `X \| None` (not Optional), Google docstrings, no `print()` in lib code |
| Commits | Conventional (`feat:` `fix:` `chore:` `docs:` `refactor:`) |
| ADR style | Numbered `D-NN` entries in vault |
| Experiment log | Numbered `R-NN` entries in RESEARCH_LOG |
| Frontend | React 19, TypeScript 6, Tailwind 4, Vite 8 |

---

## Status

**Phase 0:** Research & vault build-up — ✅ complete (22 vault notes, 5 books ingested)
**Phase 1:** Data spine & analytical framework — ✅ substantively complete (35 research rounds, 30 decisions, 2D org-quality map shipped)
**Phase 2:** Context-aware valuation model — 🔄 in progress
  - V3 single-level Bayesian live (R-33/34/35 proved V2 multilevel adds nothing)
  - Savage Analytics SPA shipped (v0.1) with 7 routes + full component library
  - Q-series experiments underway (contention window, outcome window optimization)
  - Spotrac empirical $/WAR curve live; MiLB + prospects ingest added

**Phase 3:** GM-behavior layer (predict-the-trade) — ☐ later
**Phase 4:** Product surface (public-facing) — ☐ later
**Phase 5+:** Persona critique agents — ☐ later

Current breakpoint: **R-35 + V3 model + Savage Analytics SPA v0.1.** Phase 2 build sequence is documented in [`docs/PHASE1_SYNTHESIS.md`](docs/PHASE1_SYNTHESIS.md).

---

## License

TBD. Internal/personal research project.

---

*Built with creative latitude over many sessions of pair-research with Claude Code. The project's data and methodology decisions are documented; every R-NN is reproducible; every claim has receipts. If you want to follow the thread, start at [`docs/PHASE1_SYNTHESIS.md`](docs/PHASE1_SYNTHESIS.md).*
