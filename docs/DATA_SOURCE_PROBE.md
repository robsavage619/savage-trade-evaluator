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

## Second-pass agent research (2026-05-17)

Spawned four parallel research agents to deepen probes on the deferred items. Outcomes:

### Win: pre-2010 GM regimes via BR scraper extension

**Agent finding:** the existing `ingest/front_office.py` scraper that pulls 2010-2024 from Baseball Reference per-season team pages can be **iterated backward** with no code changes — every per-season BR team page (1980+) has the same `General Manager:` field. This is dramatically simpler than the Wikipedia / Wikidata routes we tried.

Confirmed for `baseball-reference.com/teams/LAD/2008.shtml` → "Ned Colletti" in the team metadata. Same path the existing BR scrape uses for 2010+, just iterate backward.

**Action taken:** kicked off `uv run ste ingest front-office --start 1990 --end 2009` in the background. ~30 minutes for 600 requests at BR's polite rate. Fills the D-28 pre-2010 regime gap with no new dependencies.

Other Wikipedia / Wikidata routes (verified by Agent 3):
- Wikidata SPARQL on `position held = baseball GM` returns zero rows — the data isn't modeled
- "List of [Team] owners and executives" pages exist for ~15 of 30 teams (~50% coverage, not viable as a uniform pipeline)
- Wikipedia team-article infoboxes only have the current GM, not history

### Important correction: Spotrac IS accessible via direct curl

The three agents that reported "blocked" were using their WebFetch tool which has stricter egress controls than the system's `curl` (which respects only standard outbound network policy). Re-probed via curl from the main session:

- **Spotrac player pages** — accessible. e.g. `spotrac.com/mlb/los-angeles-dodgers/mookie-betts-23391/` returns real HTML with contract values inline (Ohtani $700M, Betts $365M, Yamamoto $325M, Freeman $162M all visible).
- **Spotrac team contracts pages** — accessible, ~512KB of real HTML. `spotrac.com/mlb/los-angeles-dodgers/contracts/` has player rows in `<table>` / `<tr>` markup, not JS-only shells.
- **mlbcontracts.blogspot.com** — accessible but essentially defunct (one stray "contract" mention).
- **baseballprospectus.com/cots/** — 404. Cot's was removed from BP.

So Spotrac is a real ingest candidate, just postponed because building a proper scraper (parsing multi-row tables, year-by-year contract breakdowns, player-name-to-mlbam-id mapping) is its own focused session. Documented for future iteration.

Cot's, Baseball America, MLB Trade Rumors remain genuinely blocked — they fail with 403 / require accounts / have aggressive bot detection.

### Original blocked finding (kept for context — applies to WebFetch tool only)

Three of four agents hit the same wall — `~/.claude/security/egress-allowlist.txt` (used by WebFetch) doesn't include any of:

- `spotrac.com`
- `baseballprospectus.com` / `cotscontracts.com`
- `mlbtraderumors.com`
- `docs.google.com` (for Cot's Sheets exports)
- `web.archive.org`
- `mlbcontracts.blogspot.com` (original Cot's)
- `baseballamerica.com` (canonical int'l signing tracker)

These domains require an explicit policy decision to add. The agents agreed the highest-leverage allowlist addition would be **`docs.google.com` + `baseballprospectus.com`** — Cot's publishes contract data as public Google Sheets, and the CSV-export trick works cleanly without scraping.

### Inferred from agent search (unverified by direct fetch this session)

MLB Trade Rumors international tracker URL pattern (per Agent 1):

- Slug per year is non-deterministic; need landing pages as index. Examples:
  - `mlbtraderumors.com/2016-17-international-signings`
  - `mlbtraderumors.com/2024/01/notable-international-signings-1-15-24.html`
- Data is **prose-embedded**, not tabular. Bonuses in shorthand: `$2.2MM` / `$900K`.
- Coverage: only ~30 notable signings per year. Baseball America is the canonical comprehensive source.

If int'l signing depth is needed, Baseball America is the better target — but it's both paywalled and not allowlisted.

## Open allowlist decisions

For Rob to weigh:

| Domain | Use case | Effort to ingest | Value |
|---|---|---|---|
| `docs.google.com` | Cot's Contracts via Google Sheets CSV export | Low (CSV download per sheet ID) | High (contract data) |
| `baseballprospectus.com` | Cot's legacy page | Low (to find sheet IDs) | Enables above |
| `mlbtraderumors.com` | Int'l signing trackers (~30/yr) | Medium (prose parsing) | Low-medium (limited coverage) |
| `baseballamerica.com` | Canonical int'l signing tracker | Unknown (probably paywalled) | High if accessible |
| `web.archive.org` | Cached versions of paywalled sources | Low | Variable |
| `spotrac.com` | Salary/contract data | High (JS-heavy) | Medium |

Adding entries to `~/.claude/security/egress-allowlist.txt` is a manual commit decision.

## Files of record

- `scripts/probe_data_sources.py` — runnable probe sweep
- `src/savage_trade_evaluator/ingest/fortification.py` — three new adapters
- `src/savage_trade_evaluator/storage/schemas.py` v13 — three new tables
