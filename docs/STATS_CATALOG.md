# Stats catalog

Every stat source this project knows how to reach. The source of truth is
[`ingest/catalog.py`](../src/savage_trade_evaluator/ingest/catalog.py); this file
mirrors it, with row counts measured against the live store.

Browse interactively: `uv run ste catalog`, or `uv run ste catalog --status ingested`.

**50 sources: 42 ingested, 4 available and not yet wired, 4 blocked.**

---

## Ingested

Row counts are live as of the last measurement.

| Source | Provider | Granularity | Era | Table | Rows |
|---|---|---|---|---|---|
| `statcast-batter-exitvelo-barrels` | baseball-savant | player-season | 2015-now | `statcast_batter_exitvelo_barrels` | 3,004 |
| `statcast-batter-percentile-ranks` | baseball-savant | player-season | 2015-now | `statcast_batter_percentile_ranks` | 7,621 |
| `statcast-batting-expected` | baseball-savant | player-season | 2015-now | `statcast_batting_expected` | 9,678 |
| `statcast-catcher-framing` | baseball-savant | player-season | 2015-now | `statcast_catcher_framing` | 770 |
| `statcast-catcher-poptime` | baseball-savant | player-season | 2015-now | `statcast_catcher_poptime` | 936 |
| `statcast-outfielder-jump` | baseball-savant | player-season | 2016-now | `statcast_outfielder_jump` | 1,072 |
| `statcast-outs-above-average` | baseball-savant | player-season | 2016-now | `statcast_outs_above_average` | 3,029 |
| `statcast-pitch-movement` | baseball-savant | player-season | 2015-now | `statcast_pitch_movement` | 21,532 |
| `statcast-pitcher-arsenal-stats` | baseball-savant | player-season | 2015-now | `statcast_pitcher_arsenal_stats` | 16,927 |
| `statcast-pitcher-percentile-ranks` | baseball-savant | player-season | 2015-now | `statcast_pitcher_percentile_ranks` | 7,994 |
| `statcast-pitcher-pitch-arsenal` | baseball-savant | player-season | 2015-now | `statcast_pitch_movement` | 21,532 |
| `statcast-pitching-expected` | baseball-savant | player-season | 2015-now | `statcast_pitching_expected` | 9,591 |
| `statcast-sprint-speed` | baseball-savant | player-season | 2015-now | `statcast_sprint_speed` | 6,602 |
| `bwar-batting` | bref-bwar | player-season-stint | 1871-now | `bwar_batting` | 126,684 |
| `bwar-pitching` | bref-bwar | player-season-stint | 1871-now | `bwar_pitching` | 57,776 |
| `amateur-draft` | bref-other | draft | 1965-now | `draft_picks` | 47,354 |
| `front-office` | bref-other | team-season | 1990-now | `front_office` | 3,783 |
| `standings` | bref-other | standings | 2010-now | `standings` | 1,088 |
| `chadwick-register` | chadwick | player-career | 1871-now | `chadwick_register` | 129,012 |
| `fangraphs-batting-leaders` | fangraphs | player-season | 2010-now | `fangraphs_batting_leaders` | 20,503 |
| `fangraphs-pitching-leaders` | fangraphs | player-season | 2010-now | `fangraphs_pitching_leaders` | 11,425 |
| `fangraphs-prospects` | fangraphs | player-season | 2017-2026 | `prospect_rankings` | 498 |
| `mlb-pipeline-prospects` | mlb-pipeline | player-season | 2026-now | `mlb_pipeline_prospects` | 190 |
| `coaches` | mlb-stats-api | team-season | 2010-now | `coaches` | 6,238 |
| `milb-player-stats` | mlb-stats-api | player-season-stint | 2010-now | `milb_player_seasons` | 126,306 |
| `mlb-awards` | mlb-stats-api | player-season | 1990-now | `mlb_awards` | 1,790 |
| `mlb-people` | mlb-stats-api | player-career | 1871-now | `mlb_people` | 23,710 |
| `mlb-venues` | mlb-stats-api | reference | 1871-now | `mlb_venues` | 1,646 |
| `team-40man-rosters` | mlb-stats-api | team-season | 2010-now | `team_rosters` | 25,676 |
| `team-season-stats` | mlb-stats-api | team-season | 2010-now | `team_season_stats` | 3,264 |
| `transactions` | mlb-stats-api | transaction | 2010-now | `transactions` | 832,505 |
| `mlbtr` | mlbtraderumors | reference | 2005-now | `trade_rumors` | 102,699 |
| `retrosheet-events` | retrosheet | player-game | 1921-2024 | `retrosheet_game_appearances` | 290,277 |
| `retrosheet-gamelogs` | retrosheet | team-game | 1990-now | `game_logs` | 80,798 |
| `retrosheet-parks` | retrosheet | reference | 1871-now | `retrosheet_parks` | 260 |
| `retrosheet-transactions` | retrosheet | transaction | 1880-2022 | `transactions` | 832,505 |
| `spotrac-player-contracts` | spotrac | player-season | 2011-now | `spotrac_player_contracts` | 1,152 |
| `spotrac-team-payroll` | spotrac | team-season | 2011-now | `spotrac_team_payroll` | 480 |
| `tjstats-scout-batters` | tjstats | player-career | 2026-now | `tjstats_scout_batters` | 364 |
| `tjstats-scout-pitchers` | tjstats | player-career | 2026-now | `tjstats_scout_pitchers` | 251 |
| `tjstats-tjbat` | tjstats | player-season | 2024-now | `tjstats_tjbat` | 497 |
| `tjstats-top-prospects` | tjstats | player-season | 2026-now | `tjstats_prospect_rankings` | 400 |

Two sources share the `transactions` table: `transactions` (MLB Stats API, 2010
onward) and `retrosheet-transactions` (1880-2009). The row count is the union.
`statcast-pitcher-pitch-arsenal` and `statcast-pitch-movement` likewise share
`statcast_pitch_movement`.

---

## Available, not yet wired

Adapters to write when a matching feature becomes load-bearing.

| Source | Provider | Granularity | Era | Note |
|---|---|---|---|---|
| `statcast-pitch-by-pitch` | baseball-savant | pitch-level | 2008-now | Every pitch since 2008. The base layer everything else aggregates from. Very large; defer until a feature needs something the leaderboards cannot give. |
| `team-batting-bref` | bref-other | team-season | 1871-now | Team-level seasonal aggregate. Org-level dev-fit signals at this level too. |
| `team-pitching-bref` | bref-other | team-season | 1871-now | Team-pitching aggregate. Pair with team-batting for season-level org features. |
| `tjstats-draft-rankings` | tjstats | draft | 2026-now | TJStats' own draft prospect rankings. Current cycle only. |

---

## Blocked

| Source | Provider | Why | Substitute |
|---|---|---|---|
| `baseball-america-prospect-rankings` | manual | full top-100 archive is behind a subscription | FanGraphs The Board (`prospect_rankings`) and TJStats |
| `lahman-batting` | lahman | pybaseball's Lahman auto-fetch raises a zip unpack error | bWAR covers every use case so far |
| `lahman-pitching` | lahman | pybaseball's Lahman auto-fetch raises a zip unpack error | bWAR covers every use case so far |
| `lahman-salaries` | lahman | pybaseball's Lahman auto-fetch raises a zip unpack error | Spotrac for 2011 onward; bWAR carries a salary column |

---

## FanGraphs: no longer blocked

FanGraphs used to be listed here as Cloudflare-gated, and for direct scraping
it still is: pybaseball, httpx with browser headers, `curl_cffi` with Chrome TLS
impersonation, and `cloudscraper` all return 403. The gate was cleared instead by
routing through a Firecrawl stealth proxy against the JSON leaderboard endpoint.
Batting and pitching leaderboards are backfilled 2010-2024, and The Board's
preseason FV grades are cached for 2017-2024. This needs `FIRECRAWL_API_KEY`.

Do not try pybaseball against FanGraphs. The tables already hold the data.

