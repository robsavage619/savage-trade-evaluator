# iMac cutover

The iMac runs a daily refresh at 05:30 and serves the built site on the tailnet. The laptop stays the place you develop.

## What runs there

- `com.savage.ste-refresh`: `scripts/refresh-ste.sh` at 05:30. Ingests, runs the quality gates, exports, builds, swaps the site.
- `com.savage.ste-web`: `deploy/serve_spa.py` on `127.0.0.1:8097`, exposed by `tailscale serve --bg --https=8444 8097`, which gives https://shc-imac.tail9735c5.ts.net:8444 (443 and 8443 already belong to other apps; never serve on the default port).

## The gates (src/savage_trade_evaluator/quality.py)

A failed gate leaves the last good site serving and exits 1. A warn gate publishes and shows "degraded".

| Gate | Fails when |
|---|---|
| fresh:* | a current-season table was not rewritten by this run (the frozen-row bug) |
| standings, rosters | not 30 clubs, impossible records, a roster under 25 |
| transactions:recent | newest transaction older than 7 days |
| no-shrink, war-only-grows, games/wins-only-grow | the data went backwards against the last good run |

The footer pill reads `/status.json`: green ok, amber degraded or older than 36 hours, red failed (and says it is serving older data).

## Deploy (you run it; nothing here pushes to git)

1. Commit your pending work. The deploy ships `HEAD` only, so uncommitted changes do not travel.
2. Copy the database once, by hand: `data/duckdb/trades.db` to the same path on the iMac (about the size of the file; stop any laptop ingest first, DuckDB holds a write lock).
3. `deploy/imac.sh user@imac-host` syncs the tree, installs deps, builds, and prints the sudo block.
4. Run the printed sudo block on the iMac (installs both LaunchDaemons, then `tailscale serve --bg --https=8444 8097`, which gives https://shc-imac.tail9735c5.ts.net:8444 (443 and 8443 already belong to other apps; never serve on the default port)).
5. Check: `uv run python scripts/refresh_daily.py --gates-only --since <today>T00:00:00` on the iMac, then open the tailnet URL.

## After cutover

- Two writers on two copies of the DB will diverge. Pick one for ingests; the iMac is the one that refreshes daily.
- `frontend/dist/brief-inbox` is carried across rebuilds, but a redeploy from the laptop does not touch it.
- Known lag: Spotrac throttles with 403s partway through the per-player `spotrac_contract_terms` scrape, so on a bad day fewer than half the rows are rewritten and the run shows "degraded", not failed.
