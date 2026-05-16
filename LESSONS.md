# Lessons Learned

Things we've discovered the hard way. New entries go on top, dated.

---

## 2026-05-15

### Data-source blockers

- **FanGraphs is gated by Cloudflare.** Tried pybaseball (legacy endpoint), direct httpx with browser headers, `curl_cffi` with Chrome120 TLS impersonation, and `cloudscraper` Cloudflare JS-challenge solver. **All hit 403.** The only viable route is Playwright (real headless browser) which is heavy and fragile. **Substitute: bWAR (Baseball Reference) for WAR and value components; Baseball Savant Statcast for xwOBA / xERA / arsenal data.** Don't waste cycles re-trying FG without Playwright — track this in the catalog as `blocked=True`.

- **Lahman auto-fetch is broken in pybaseball.** `pybaseball.lahman.*` raises `BadZipFile`. The Chadwick Bureau GitHub mirror returns 404 on all expected paths. Workaround: download Lahman CSVs manually. We haven't needed Lahman yet (bWAR covers the same era better), so it's deferred indefinitely.

- **MLB Stats API transactions coverage starts effectively 2010** (D-14). Pre-2009: 1 trade event across 1990-2008 combined. 2009: 24K rows including 289 trade events. 2010+: 30K-75K/year. V1 backtester scope therefore is 2010-2024 for trade events.

- **MLB API has coaches, not GMs.** `/teams/{id}/coaches?season=Y` returns the full coaching staff (manager + bench/hitting/pitching/bullpen/base coaches). It does NOT return front-office executives. Use Baseball Reference per-season team pages for that (D-15).

### Performance wins

- **DuckDB pandas registration is ~70× faster than executemany for bulk inserts with ON CONFLICT.** Per-row INSERT for 62,800 transactions took 68 seconds. Switching to `conn.register("staging", df)` + `INSERT INTO target SELECT * FROM staging ON CONFLICT...` dropped it to 1 second. Always use the staging-DataFrame pattern for batch inserts.

- **httpx connection pooling** matters when looping over hundreds of API calls. `httpx.Client()` once, reuse across the loop — not a new client per request.

### Schema gotchas

- **MLB Stats API `transaction_id` is a *trade-event* identifier**, not a row identifier. Multi-player trades share an ID across legs (Pressly MIN→HOU is 3 rows, all `transaction_id=371509`). Our V0 schema used it as PRIMARY KEY which silently dropped the 2nd and 3rd legs of every multi-player trade. **Fixed with composite PK `(transaction_id, leg_index)`** and a `_normalize_all` function that assigns sequential leg indices per shared ID.

- **bWAR uses Baseball Reference team codes** ("HOU", "MIN", "KCR", "SDP") while MLB Stats API uses integer team IDs (117, 142, 118, 135). **8 of 30 teams have divergent abbreviations** — MLB API "AZ" vs bWAR "ARI"; "ATH" vs "OAK"; "CWS" vs "CHW"; "KC" vs "KCR"; "SD" vs "SDP"; "SF" vs "SFG"; "TB" vs "TBR"; "WSH" vs "WSN". The `teams` table is the canonical bridge.

- **Pitchers appear in bWAR batting too.** Don't naively UNION ALL bwar_batting + bwar_pitching and join by (mlb_id, year) — you'll get Cartesian explosion in trade-WAR window queries. Aggregate WAR across roles per (mlb_id, year) FIRST, then join.

### Empirical findings (data tells us things)

- **COVID-2020 distorts 2021 trade analysis (D-17).** The 60-game 2020 season suppresses T-1 WAR baselines for the 2021 trade cohort. Naive ≥2 WAR cutoff catches 30 trades in 2015 but only 2 in 2021 — not because trade quality changed, but because the prior-season-WAR distribution is shifted. Backtester needs games-adjusted WAR thresholds OR an exclusion period.

- **The Pressly thesis is empirically visible in V1 data.** fb_spin percentile 97→98 (stuff unchanged), curve_spin 100→100 (stuff unchanged), K% percentile 65→94, whiff% 69→95 (pitch *usage* changed). The MVP Machine Ch 9 narrative is a Statcast-arsenal-window query away.

### Process

- **The catalog scaffolding paid off immediately.** Adding new data sources became a 4-step routine instead of an ad hoc choice: (1) add `StatSource(...)` entry to `catalog.py`, (2) write adapter in `ingest/<source>.py`, (3) add schema in `schemas.py` (bump version), (4) add CLI subcommand. Documenting *what we could ingest* before *what we have ingested* prevented premature commitments to WAR-as-outcome.

- **DuckDB exclusive lock blocks all concurrent ops.** Background ingest + foreground analyze = `IO Error: Conflicting lock`. For multi-hour ingests, serialize. We learned this the hard way during the BR front-office scrape.

- **BR rate-limiting is real.** ~20 requests/minute per their guidelines. Our `RATE_LIMIT_SECONDS = 3.5` for the 450-request 2010-2024 front-office scrape took ~26 minutes. Don't try to be cute — respect the limit; the data is reliably there.
