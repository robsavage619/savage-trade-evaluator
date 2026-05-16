# Stats Catalog

What metrics determine trade success? We don't yet know. This catalog inventories every stat source we know how to reach so we can pull any of them in when a feature becomes load-bearing. Source of truth is [`src/savage_trade_evaluator/ingest/catalog.py`](../src/savage_trade_evaluator/ingest/catalog.py); this doc mirrors it.

Browse interactively: `uv run ste catalog`.

**Status legend:** ✅ ingested · ☐ available, not yet wired · ⛔ blocked.

---

## Currently ingested (V1 spine)

| Stat | Source | Granularity | Era | Notes |
|---|---|---|---|---|
| **transactions** | MLB Stats API | per transaction | 2010-* | Trades + signings + releases + status changes |
| **bwar-batting** | Baseball Reference | player-season-stint | 1871-* | WAR + off/def runs + WAR_rep + WAA + salary |
| **bwar-pitching** | Baseball Reference | player-season-stint | 1871-* | WAR + ERA+ + RA + xRA + WAA |
| **statcast-batting-expected** | Baseball Savant | player-season | 2015-* | xwOBA, xBA, xSLG (luck-adjusted baselines) |
| **statcast-pitching-expected** | Baseball Savant | player-season | 2015-* | xwOBA + xERA (FIP substitute) |
| **statcast-pitcher-percentile-ranks** | Baseball Savant | player-season | 2015-* | fb_velocity, fb_spin, curve_spin, k% / bb% / whiff% / chase% — dev-fit arsenal |

---

## Available, not yet wired

Wire these up as adapters when a corresponding feature becomes important.

### Statcast leaderboards (Baseball Savant)

| Stat | Granularity | Era | When to wire |
|---|---|---|---|
| **statcast-batter-percentile-ranks** | player-season | 2015-* | When batter dev-fit becomes load-bearing alongside pitcher (xwOBA, barrel%, exit velo, sprint speed percentiles) |
| **statcast-batter-exitvelo-barrels** | player-season | 2015-* | Quality-of-contact detail (avg/max hit speed, barrel rate) |
| **statcast-pitcher-arsenal-stats** | player-season | 2015-* | Per-pitch-type breakdown — reveals which pitches an org's dev system actually fixed |
| **statcast-pitcher-pitch-arsenal** | player-season | 2015-* | Per-pitch movement profiles (velocity, spin, vertical/horizontal break). Pitch-design feature space. |
| **statcast-sprint-speed** | player-season | 2015-* | Baserunning dev signal |
| **statcast-outs-above-average** | player-season | 2016-* | Modern defensive metric (replaces UZR/DRS as Statcast's def-WAR component) |
| **statcast-catcher-framing** | player-season | 2015-* | Catcher receiving + pitch framing |
| **statcast-catcher-poptime** | player-season | 2015-* | Catcher throwing-to-2B (pop time, exchange, arm strength) |
| **statcast-outfielder-jump** | player-season | 2016-* | OF dev signal — breakdown of how OAA gets earned |

### Pitch-level raw

| Stat | Granularity | Era | When to wire |
|---|---|---|---|
| **statcast-pitch-by-pitch** | pitch-level | 2008-* | Every pitch since PITCHf/x launch. **Very large.** Defer until we need a feature we can't get from leaderboards. |

### Player ID bridges + cross-source

| Stat | Granularity | Era | When to wire |
|---|---|---|---|
| **chadwick-register** | player-career | 1871-* | When we need cross-source joins beyond bWAR↔Statcast (e.g., Retrosheet, BA archives) |

### Historical / Lahman

⛔ pybaseball's Lahman auto-fetch is broken (zip-file unzip error). Workaround = manually download Lahman CSVs.

| Stat | Era |
|---|---|
| lahman-batting | 1871-* |
| lahman-pitching | 1871-* |
| lahman-salaries | 1985-2016 (then truncated; Cot's is more current) |

### Draft + amateur

| Stat | Granularity | Era | When to wire |
|---|---|---|---|
| **amateur-draft** | per-draft-pick | 1965-* | Required for position-class × source-class baselines (D-11). One year at a time. |

### Team-season aggregates

| Stat | Granularity | Era | When to wire |
|---|---|---|---|
| **team-batting-bref** | team-season | 1871-* | Org-level dev-fit features at team aggregate level |
| **team-pitching-bref** | team-season | 1871-* | Pair with team-batting for season-level org features |
| **standings** | team-season | 1901-* | Contention-window features; backfill playoff probability |

---

## Blocked sources (need workaround)

### FanGraphs — Cloudflare-gated

⛔ Tried pybaseball / httpx with browser headers / `curl_cffi` / `cloudscraper` — all hit 403 from Cloudflare. Only viable route: Playwright (heavy, deferred until specifically needed).

| Stat | Substitute we use instead |
|---|---|
| **fangraphs-batting-leaders** (wRC+, wOBA, fWAR, Off, Def, Bat, Fld, Pos, BsR) | bWAR + Statcast est_woba |
| **fangraphs-pitching-leaders** (FIP, xFIP, SIERA, fWAR, K%, BB%, GB%) | bWAR + Statcast xERA + percentile ranks |
| **fangraphs-prospects** (FV, Risk, ETA, tool grades) | **No public substitute.** Will need Playwright when Phase 2 prospect work starts. |

### Baseball America

⛔ **baseball-america-prospect-rankings** — BA top-30 lists are public most years; full top-100 archive requires subscription. archive.org has older issues.

---

## How to add a new source

1. Append a `StatSource(...)` entry to `CATALOG` in [`catalog.py`](../src/savage_trade_evaluator/ingest/catalog.py).
2. If wiring an active adapter:
   - Write a fetcher function in `src/savage_trade_evaluator/ingest/<source>.py`.
   - Add a schema in `src/savage_trade_evaluator/storage/schemas.py` and bump `SCHEMA_VERSION`.
   - Add a CLI subcommand in `cli.py`.
   - Flip `ingested=True` and set `target_table=...` in the catalog entry.
3. Update this markdown mirror (or regenerate it from the catalog when we automate that).

## Programmatic access

```python
from savage_trade_evaluator.ingest import catalog

catalog.ingested()                                # working adapters
catalog.available_not_yet_ingested()              # scaffolded but no adapter
catalog.blocked()                                 # known blockers
catalog.covers_year(2018)                         # everything available for 2018
catalog.by_source("baseball-savant")              # all Savant entries
catalog.by_granularity("pitch-level")             # pitch-by-pitch sources
catalog.search("spin")                            # substring search across name/notes/columns
```
