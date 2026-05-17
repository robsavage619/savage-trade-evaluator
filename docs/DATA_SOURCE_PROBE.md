# Data Source Probe (2026-05-16)

Systematic web-probe of 24 candidate data sources we'd referenced but never confirmed. Goal: identify what's accessible, what's blocked, and what's worth ingesting next.

Reproducible via `uv run python scripts/probe_data_sources.py`.

## Summary

| Status | Count | Notes |
|---|---|---|
| ✅ accessible | 16 | Confirmed HTTP-accessible with browser-style headers |
| ⛔ blocked | 2 | FanGraphs Cloudflare-gated (confirms D-25) |
| ❌ 404 | 4 | URLs wrong — see "URL corrections" below |
| ⚠️ errors | 1 | Sean Lahman host connect-error |

## High-leverage ingests added (this pass)

| Source | Adapter | Coverage | Rows |
|---|---|---|---|
| **Chadwick Register** | `ingest/fortification.py::ingest_chadwick_register` | All-time players with MLB IDs | **127,526** |
| **Statcast catcher framing** | `ingest/fortification.py::ingest_catcher_framing_range` | 2015-2024 | 580 |
| **MLB Stats API awards** | `ingest/fortification.py::ingest_awards_range` | 1990-2024, 17 award types | 1,734 |

### Why these three

- **Chadwick gives us real birth dates.** 96.6% of our 23,622 bWAR players now have birth_year/month/day. Replaces the years-since-debut age proxy across all R-13/R-25/R-27/R-29/R-30 work. Also provides clean MLBAM↔Retro↔BRef↔Fangraphs ID cross-walk for future joins.
- **Catcher framing** was a previous gap (pybaseball CSV-parse failed). Direct fetch from Savant CSV works. Lets us decompose pitcher xERA improvements into "real" gains vs catcher-framing artifact — directly addresses an R-22 caveat.
- **Awards** opens prospect-pedigree features ("did the team that drafted X also win ROY for him?"). MVP/CY/ROY/GG/SS recipients per season per league. 1,734 rows.

## Accessible sources NOT ingested this pass

Documented for future iteration. URL + format confirmed but ingest deferred to keep the pass scoped.

| Source | URL | Why deferred |
|---|---|---|
| Retrosheet game logs | `retrosheet.org/gamelogs/` | Gigabytes; need for Pinheiro-Szymanski mean-variance is Phase 2+ |
| Retrosheet event files | `retrosheet.org/game.htm` | Same scope concern |
| Wikipedia per-team articles | `en.wikipedia.org/wiki/<Team>` | Useful for pre-2010 regime boundaries; HTML scraping non-trivial |
| MLB.com transactions feed | `mlb.com/transactions` | Different shape than MLB Stats API — redundant with what we have |
| Spotrac MLB | `spotrac.com/mlb/` | Salary data; not yet on the critical path |
| Cot's Contracts | `legacy.baseballprospectus.com/cots/` | Page-of-links to Google Sheets; non-trivial |
| Savant sprint-speed leaderboard | `baseballsavant.mlb.com/sprint_speed_leaderboard` | Already in `statcast_batter_percentile_ranks` |
| MiLB.com prospects | `mlb.com/milb/prospects` | Lazy-loaded JS — requires Playwright (confirmed R-26) |
| Baseball Cube | `thebaseballcube.com` | Public but no clear API; would need targeted scraping |
| BR per-team season transactions | `baseball-reference.com/teams/LAD/2023.shtml` | We already scrape BR for front-office |
| MLB Stats API awards index | `statsapi.mlb.com/api/v1/awards` | Ingested (the recipients endpoint) |
| MLB Stats API schedule | `statsapi.mlb.com/api/v1/schedule` | Different scope; available if needed |

## Confirmed-blocked sources

| Source | URL | Status |
|---|---|---|
| FanGraphs leaders (HTML) | `fangraphs.com/leaders.aspx` | 403 — Cloudflare-gated (D-25 still holds) |
| FanGraphs CSV API endpoint | `fangraphs.com/api/leaders/...` | 403 — same gate |
| FanGraphs prospect grades | `fangraphs.com/prospects/the-board/...` | 500 (likely Cloudflare challenge) |

## URL corrections (404s → fixed)

| Source | Wrong URL | Correct URL |
|---|---|---|
| Chadwick people.csv | `chadwickbureau/register/.../people.csv` (deprecated path) | 16 sharded files: `people-{0-9,a-f}.csv` |
| Lahman GitHub | `chadwickbureau/baseballdatabank` (repo deleted) | Use `jknecht/baseball-archive-sqlite` or Chadwick directly |
| MLB Trade Rumors int'l tracker 2024 | Posted-URL guess | Annual posts move — would need search via site |
| Cot's Google Sheets | Guessed sheet ID | Real ID would need lookup from Cot's HTML page |

## Birth-date downstream impact

Before this pass, age was proxied via `trade_season - first_mlb_year` (years-since-debut). With Chadwick we now have actual age = `trade_season - birth_year`. This:

- Removes the late-bloomer / early-debut bias from R-13's `β_exp` covariate
- Enables a proper "age curve" feature distinct from MLB experience
- Lets us re-bucket VET-AT-PEAK and YOUNG-PROSPECT (D-29) on age, not just experience
- Coverage: 22,821 of 23,622 bWAR players (96.6%) have full birth-year. Pre-1900 / Negro League / unverified records make up the remaining 3%.

## Next-pass candidates (deferred)

1. **MLB Trade Rumors annual international signing tracker** — find correct URL for each year, scrape names + bonuses. Replaces the current "post-1995 not in draft_picks" proxy with real attribution.
2. **Wikipedia GM/POBO tenure tables** — clean pre-2010 regime boundaries by scraping per-team articles.
3. **Retrosheet event logs** — pitch-by-pitch data for Pinheiro-Szymanski mean-variance replication.
4. **Spotrac contracts** — salary data for the surplus-value baseline.
5. **MLB Pipeline top-100 prospects** — Playwright-based scrape (lazy-loaded JS).
6. **fWAR via FanGraphs alt-route** — try `r.fangraphs.com` or archive.org cached snapshots.

## Files of record

- `scripts/probe_data_sources.py` — runnable probe sweep
- `src/savage_trade_evaluator/ingest/fortification.py` — three new adapters
- `src/savage_trade_evaluator/storage/schemas.py` v13 — three new tables
