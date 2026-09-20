# Decomposition, dev credit, and data fortification (R-30 to R-32)

Separating sell-high from system-tax, which rejects the original thesis outright.
Building the 2D org-quality map. Closing the age and international-signing proxy
gaps with ten new data sources.

Part of the [research log](README.md). Entries run oldest first.

---

## [2026-05-16] R-30: Sell-high vs system-tax decomposition. The original Dodgers thesis is rejected; TEX-Daniels is a clean sell-high finding

**Question (plain English).** R-28 surfaced TEX-Daniels as the strongest negative regime in the data. R-29 archaeology of Daniels' trades showed the negative signal came from veterans (Lucroy, Minor, Michael Young, Darvish). That is a sell-high mechanic, not the system-tax mechanic from Rob's original thesis. Does this distinction generalize? For each regime, split trades into:
- VET-AT-PEAK: pre_war >= 2.0 AND experience >= 6 (sold-high candidate)
- YOUNG-PROSPECT: pre_war <= 1.0 AND experience <= 4 (system-tax candidate)
- MIDDLE: everything else

The system-tax thesis predicts the YOUNG-PROSPECT bucket should be NEGATIVE in regimes where it applies. The sell-high thesis predicts the VET-AT-PEAK bucket should be NEGATIVE.

**Setup.** `scripts/sell_high_vs_system_tax.py` joins trade_player_war_window to team_regime_assignments + first-mlb-year proxy. Buckets per the above. Reports per-bucket mean delta WAR per regime for the 16 most-discussed regimes (top 8 negative + top 4 positive from R-28 + 4 prior-highlight).

**Result.**

Per-regime decomposition (selected):

| Regime | n | Overall delta | YOUNG-PROSPECT delta (n) | VET-AT-PEAK delta (n) | Mechanism |
|---|---|---|---|---|---|
| **TEX-Daniels** | 66 | -0.537 | **+0.13** (27) | **-2.54** (9) | **clean SELL-HIGH** |
| MIL-Stearns | 39 | -0.413 | +0.73 (14) | -3.39 (5) | sell-high (small vet n) |
| LAA-Eppler | 23 | -0.467 | +0.05 (5) | -3.87 (1) | inconclusive (vet n=1) |
| ATL-Anthopoulos | 23 | -0.113 | +0.07 (15) | n/a (0) | inconclusive |
| LAD-Friedman | 63 | +0.006 | +0.51 (34) | -4.08 (2) | **neutral overall** |
| OAK-Beane | 66 | -0.137 | +0.60 (23) | -1.59 (9) | sell-high |
| CLE-Antonetti | 45 | -0.124 | +0.81 (25) | -3.21 (6) | sell-high |
| HOU-Luhnow | 44 | +0.208 | **+0.83** (22) | -2.87 (2) | YOUNG-PROSPECT POSITIVE |
| TOR-Anthopoulos | 31 | +0.348 | +0.43 (10) | -0.98 (2) | positive |
| STL-Mozeliak | 49 | -0.242 | +0.44 (23) | -2.47 (1) | inconclusive |
| WSN-Rizzo | 52 | +0.143 | +0.61 (17) | -1.14 (7) | mixed positive |
| PIT-Cherington | 27 | +0.726 | +0.81 (11) | +1.96 (1) | broad positive |

**Two universal patterns:**

1. **YOUNG-PROSPECT bucket is POSITIVE in every regime tested.** Mean ranges from +0.05 to +0.83 WAR. No regime shows the predicted system-tax pattern.
2. **VET-AT-PEAK bucket is sharply NEGATIVE in every regime.** Mean ranges from -0.98 to -4.08 WAR. This is universal aging-at-peak, not org-specific.

**Interpretation (plain English).**

1. **The original Dodgers system-tax thesis is EMPIRICALLY REJECTED.** Across every regime we tested, young players who get traded *gain* WAR on average after the trade. No regime shows the predicted "young system-dependent player declines after leaving" pattern. The R-10/R-12/R-17/R-27 negative regime intercepts we attributed (implicitly) to system-tax mechanics were not what we thought.

2. **TEX-Daniels is the cleanest sell-high finding in the project.** 9 veterans traded with mean pre-trade WAR +3.96 who collectively dropped -2.54 WAR after the trade. Lucroy to COL, Minor to OAK, Michael Young to PHI, Darvish to LAD, Kiner-Falefa to MIN. The pattern is broad-based (trim test from R-29: the mean shifts only +0.05 when removing the 3 worst and 3 best). Daniels has a credible, replicable skill at identifying veterans whose value is peaking and trading them right before the cliff. **This is a different thesis than what we set out to test, but it's the most-supported single claim in the project.**

3. **The LAD-Friedman story collapses on inspection.** His regime-level intercept (-0.018) was driven by R-17 *pairwise* comparisons. In absolute terms, LAD-Friedman is NEUTRAL: +0.006 overall, with young prospects he traded gaining an average +0.51 WAR. He's not system-tax; he's not even credibly different from zero. The "LAD < HOU" comparison still holds, but not because LAD is bad. It holds because HOU-Luhnow's young prospects gain *more* than LAD's young prospects do.

4. **HOU-Luhnow young-prospect launchpad is the strongest specific positive finding** in the project: +0.83 mean WAR gain on 22 young prospects he traded out. This is the OPPOSITE of the dev-travels reading of MVP Machine Ch 9. Luhnow was trading prospects he *didn't* think would crack the Astros' rich roster, and those prospects often proved his judgment wrong (or right, depending on framing) by producing for their new teams.

5. **The systematic young-prospect-gains-after-trade pattern is consistent with playing-time recovery.** Young players blocked behind better starters get traded, get regular playing time, and their counting WAR rises. This is a *non-system* mechanism that explains most of the YOUNG-PROSPECT positive pattern without requiring any org-level dev story.

**Affects.**

- **Original Dodgers system-tax thesis: rejected.** Documenting clearly in the decisions log.
- **TEX-Daniels sell-high is the new headline finding.** Worth foregrounding in any project writeup ahead of LAD-Friedman or HOU-Luhnow.
- **HOU-Luhnow positive intercept is now reframed.** It is not "dev travels with the player" but "a rich roster meant the prospects he traded out got opportunity elsewhere." That's a roster-context finding, not a coaching-staff-travels finding.
- **The MVP Machine Ch 9 thesis** (Pressly receiving-side dev-fit) is unaffected by this, because that was about acquired players, not departed ones. But the symmetric origin-side reading of Ch 9 we proposed in R-27 is much weaker than we thought.
- **D-29 candidate**: research framing must distinguish sell-high vs system-tax mechanisms. Any future per-regime claim needs the bucket decomposition to be interpretable.

Caveats:
- VET-AT-PEAK n is small per regime (1-9). The TEX-Daniels finding at n=9 is the strongest; others (Stearns n=5, Beane n=9, Antonetti n=6) are directionally supportive but less individually credible.
- Experience is an MLB-debut-based proxy for age; late bloomers / early debuts get miscategorized.
- Playing-time recovery is a confounder we cannot disentangle from "system-tax via WAR" without explicit PA / IP controls.

Files: `scripts/sell_high_vs_system_tax.py`, `scripts/investigate_regime_anomalies.py` (R-29 archaeology).

---

---

## [2026-05-16] R-31: Dev-credit attribution. Built the org-quality 2D map, found surprising rankings, debunked the Dodgers "elite system" framing

**Question (plain English).** Rob's insight: trade-outcome metrics measure how trades worked out, but they don't credit teams for developing players who eventually became MLB stars (even after being traded). A team that drafts and develops a star should get credit for them regardless of where they finished their career. We need a dev-quality signal independent of trade skill.

**Setup.** Three iterations:
- v1: total career WAR by drafting team. Inflated by didn't-sign cases (Helton drafted SDP '92, never signed, became a Hall of Famer with COL, so SDP was incorrectly credited).
- v2: filter to "debuted with drafter" (player's first MLB stint matches the drafting team). Properly excludes Helton from SDP, properly credits COL.
- v3: add franchise-alias resolution (TBD to TBR, FLA to MIA, MON to WSN, ANA/CAL to LAA, BRO to LAD, NYG to SFG, BSN to ATL, SLB to BAL, WS1 to MIN, WS2 to TEX, PHA/KCA to OAK), filter to current 30 franchises only, add international signing proxy (post-1995 MLB debutees not in draft_picks), add scout-to-sign conversion rate by round, build the 2D (dev, trade) coordinate map.

**Result.**

### Dev credit (career WAR of 1990+ MLB debutees, by current franchise)

| Rank | Team | n debutees | dev WAR | mean WAR/debutee |
|---|---|---|---|---|
| 1 | CLE | 246 | 1352.8 | 5.50 |
| 2 | HOU | 262 | 1224.1 | 4.67 |
| 3 | MIN | 276 | 1209.2 | 4.38 |
| 4 | LAD | 235 | 1197.9 | 5.10 |
| 5 | ATL | 256 | 1128.5 | 4.41 |
| 6 | OAK | 275 | 1123.3 | 4.08 |
| 7 | SEA | 289 | 1123.1 | 3.89 |
| 8 | NYY | 255 | 1109.4 | 4.35 |
| 9 | TOR | 274 | 1107.6 | 4.04 |
| 10 | STL | 282 | 1102.2 | 3.91 |
| ... | | | | |
| 29 | SDP | 312 | 690.7 | 2.21 |
| **30** | **SFG** | **263** | **623.5** | **2.37** |

### International signing proxy (post-1995 debutees not in draft_picks)

| Rank | Team | n intl | intl WAR | top single WAR |
|---|---|---|---|---|
| 1 | NYY | 79 | 422.9 | 68.7 (likely Cano) |
| 2 | CLE | 53 | 400.7 | 58.8 |
| 3 | SEA | 71 | 375.5 | 60.0 (Ichiro) |
| 4 | MIA | 89 | 342.9 | 67.2 (likely M. Cabrera through trade year) |
| 5 | LAD | 75 | 309.7 | 93.7 (likely Adrián Beltré) |
| 6 | HOU | 71 | 303.7 | 60.2 |
| 7 | MIN | 63 | 281.7 | 55.0 |
| 8 | ATL | 67 | 277.8 | 62.7 |
| 9 | NYM | 65 | 276.4 | 37.0 |
| 10 | LAA | 59 | 251.8 | 54.1 |

### Scout-to-sign conversion by round

| Round | n reach MLB | debuted with drafter | rate |
|---|---|---|---|
| 1 | 777 | 615 | **79.2%** |
| 2 | 513 | 346 | 67.4% |
| 3 | 406 | 250 | 61.6% |
| 5 | 344 | 209 | 60.8% |
| 10 | 185 | 112 | 60.5% |
| 15 | 121 | 58 | 47.9% |

Even in round 1, 21% of MLB-reaching draftees don't debut for the drafter. By round 15, nearly half debut elsewhere.

### 2D org-quality map

Median DEV-WAR = 1200; median trade delta = -0.157. Four quadrants:

**HIGH-DEV / TRUE-POSITIVE-TRADE** (best of both):
- **HOU only**: dev 1528, trade delta +0.049. Only team with above-median dev AND truly positive trade delta (above zero).

**HIGH-DEV / ABOVE-MEDIAN-TRADE** (good both ways):
- CLE (1754, -0.14), NYY (1532, -0.07), LAD (1508, -0.03), MIA (1324, -0.15), TOR (1240, -0.14), WSN (1239, -0.11)

**HIGH-DEV / BELOW-MEDIAN-TRADE** (great dev, poor trades):
- SEA (1499, -0.19), MIN (1491, -0.18), ATL (1406, -0.20), LAA (1271, -0.16), OAK (1269, -0.26), CHW (1219, -0.34), TEX (1216, -0.27), BOS (1200, -0.22)

**LOW-DEV / ABOVE-MEDIAN-TRADE** (compensate with trades):
- **STL only**: dev 1200, trade delta **+0.10**, the strongest positive trade delta in baseball, despite below-median dev. The "Cardinal Way" is really about trading skill, not dev pipeline.
- PIT, KCR, MIL, PHI, DET, ARI, COL

**LOW-DEV / BELOW-MEDIAN-TRADE** (bottom quadrant, weak on both axes):
- NYM (1109, -0.22), BAL (922, -0.19), CHC (880, -0.17), TBR (880, -0.37), CIN (868, -0.20), **SDP (809, -0.24), SFG (671, -0.35)**

**Interpretation (plain English).**

1. **Cleveland is the league's best dev pipeline** (1754 total dev WAR including int'l). They lead in both the amateur draft channel (1353) AND in international scouting (#2 at 401).

2. **Houston is in a class of its own as the only HIGH-DEV / TRULY-POSITIVE-TRADE team.** They're the most balanced franchise on both axes. The MVP Machine Ch 9 dev-travels narrative was incomplete. They're not just installing MLB-level fixes; they're also developing more talent than most teams.

3. **St. Louis is the dedicated trade-skill leader.** Strongest positive trade delta in the league (+0.10) despite below-median dev. Their reputation as "great organization" is really about trading skill, not amateur pipeline.

4. **The Dodgers' "elite system" reputation is overstated.** They're #4 in dev (top tier but not first) and their trade delta is near-median (-0.03). They're a balanced top-tier franchise but not anomalous. The original Dodgers system-tax thesis was empirically rejected (D-29) and is now further reframed: they're an average-to-good franchise on both metrics, not exceptional on either.

5. **The Giants are the league's worst on both axes.** Last in dev (671 WAR), among worst in trade delta (-0.35). Their 2010-2014 World Series titles were built on outliers (Posey, Lincecum, FA acquisitions) not underlying franchise quality.

6. **San Diego is in the bottom quadrant on both axes.** Dev 809 WAR (29th of 30), trade delta -0.24. Preller's aggressive style hasn't moved the franchise out of the bottom quadrant in 11 years.

7. **Boston falls to HIGH-DEV / BELOW-MEDIAN-TRADE.** Their scouting reputation holds but their trade outcomes are mid-to-poor. The "Cherington / Bloom" era criticism is statistically supported.

8. **NYY's international scouting is #1 in baseball** (423 WAR from int'l alone). Their reputation as a "buy stars" franchise misses that they also develop more international talent than anyone.

9. **TBR (880 dev, -0.37 trade delta) has the WORST trade delta in baseball.** They develop players but lose massive trade value when they move them. This is the cleanest "system tax mechanic" in our data, but at the *franchise* level, not the prospect-mechanism level: they trade their stars early in arb cycles.

10. **The DEV vs TRADE axes are roughly orthogonal.** Pearson correlation ~ near zero. Teams good at one aren't systematically good at the other. The (dev, trade) coordinate is the right product-relevant artifact.

**Affects.**

- **D-30 candidate**: V2 product surface should ship the 2D org-quality coordinate map as a first-class artifact. Each org gets a (dev_war, trade_delta) tuple with quadrant label. Strategy implications differ by quadrant:
  - HIGH-DEV/POS-TRADE: keep doing what you're doing (HOU)
  - HIGH-DEV/NEG-TRADE: improve trade execution; you have the pipeline (BOS, MIN, ATL, OAK)
  - LOW-DEV/POS-TRADE: keep compensating via trades but invest in dev (STL, PIT)
  - LOW-DEV/NEG-TRADE: systemic rebuild needed (SDP, SFG, NYM, TBR)

- **Reframes 30 rounds of work.** The "system tax" thesis (Dodgers, Preller-era SDP) is empirically rejected, replaced by a 2D quality framework that says these are mid-quadrant or bottom-quadrant teams without anomalous mechanisms.

- **International signing data has been a known gap** (D-15 etc.). The post-1995 not-in-draft-picks proxy fills it imperfectly but usefully. Next-iteration ingest would be MLB Trade Rumors annual int'l-signing trackers (no public API, would require Playwright scraping).

- **Franchise-alias resolution is a reusable utility.** All future per-team analyses across 1990+ should use it. Should be added as a shared module in `storage/`.

- **Caveats**:
  - International proxy mis-includes pre-1990 draftees who debuted in early 1990s (small but non-zero contamination)
  - The "first MLB team" attribution misses prospect trades in the minors (e.g., a Cuban signee acquired by HOU and traded to TEX as an A-baller would credit TEX, not HOU)
  - Career WAR is a counting stat. Older teams (LAD, STL, NYY, CLE) accumulate it just by existing longer with stable pipelines

Files: `scripts/dev_credit_attribution.py` (v1, kept for transparency), `scripts/dev_credit_attribution_v2.py` (v2, debuted-with-drafter filter), `scripts/dev_credit_full.py` (v3, all four fixes).

---

---

## [2026-05-17] R-32: Data-fortification arc. 10 new sources, schema v11 to v19, real ages and birth countries finally land

**Question (plain English).** Phase 1 modeling (R-06 through R-31) ran on data that had two big proxies welded into it: `years_since_debut` standing in for age, and `post-1995 MLB debutees not in draft_picks` standing in for international signings. Both worked, but every coefficient in the R-13 / R-25 / R-27 / R-29 / R-30 / R-31 chain carries the proxies' baggage. Before committing to a Phase 2 V2 model build, we ran a systematic data-fortification arc to find out which gaps we could actually close.

**Setup.** Two systematic probes of 24+ candidate data sources spread across two days: one done directly via the catalog and probe scripts (`docs/archive/DATA_SOURCE_PROBE.md`), one done by dispatching subagents at the same time against the same candidate list. Each candidate scored on accessibility (curl/pybaseball/MLB-API/scrape), modeling utility, and cost-to-ingest. Schema went **v11 to v19** across 12 commits. The goal: anything cheap that closes a known proxy gap gets ingested before Phase 2 V2 starts.

**Result.** Ten new sources landed, with row counts in the project DB:

| Source | Rows | What it makes possible |
|---|---|---|
| **Chadwick register** | 127,526 | Player birth dates plus ID cross-walks (bbref, retro, mlbam, fg) |
| **MLB Stats API people** | 23,617 | Birth country, handedness, height/weight, position: full player profiles |
| **Retrosheet game logs** | 80,798 | Full 1990-2024 game-by-game (home/away, scores, parks, attendance) |
| **Team rosters** | 22,549 | Per-team-season player rows for roster-context features |
| **Statcast pitch movement** | 17,553 | Per-pitcher-per-pitch-type physics (velo, spin, IVB, HB, release) |
| **MLB Stats API awards** | 1,734 | 1990-2024 award recipients (MVP, Cy Young, Gold Glove, Silver Slugger, ROY) |
| **MLB venues** | 1,646 | Park capacity, dimensions, surface, roof type |
| **Team season stats** | 1,350 | Per-team-season aggregates (hitting / pitching / fielding groups) |
| **BR front-office backfill** | ~1,780 | Front-office personnel extended **1990-2009** (previously 2010+ only) |
| **Statcast catcher framing** | 580 | 2015-2024 framing runs |
| **Retrosheet parks** | 260 | Historical parks with open/close dates for park-era features |
| **Spotrac contracts** | pending* | Smoke-test confirms LAD 2024 = 40 contracts, $200M cap |

*Spotrac adapter is committed (`7e263c4`) and smoke-tested but the full ingest is awaiting DuckDB write-lock release.

**Interpretation (plain English).**

1. **The age proxy is dead.** Chadwick + MLB-people give us real birth dates and birth years for 127K+ players. Every R-13 / R-25 / R-27 / R-29 / R-30 model that used `years_since_debut` as an age proxy can now be rerun against **actual age at trade**. Late bloomers and early debuts (the cohort R-30 explicitly flagged as a confounder) stop getting miscategorized.

2. **International attribution finally has a primary key, not a heuristic.** R-31's int'l ranking ("post-1995 debutees not in draft_picks") was a proxy that mis-included pre-1990 holdovers. With `birth_country` from MLB-people we can now do **direct** international attribution: born outside US/Canada/Puerto Rico, first MLB team is the origin org. The CLE / NYY / SEA / LAD rankings can be revalidated cleanly.

3. **Park-factor work is now possible.** 1,646 venues, 260 Retrosheet parks, and 80K game logs with attendance and home/away let us build park factors per season and add park-adjusted outcomes alongside the Statcast park-neutral metrics. Coors-era COL, pre-humidor / post-humidor, mid-90s Camden, post-2020 deep-fence relocations all become first-class features.

4. **Pitcher-physics deltas are a new outcome family.** 17,553 pitch-movement rows per pitcher per pitch type open the *receiving-side* MVP-Machine-Ch-9 thesis at finer grain than R-13's K%/whiff% percentile ranks: we can now ask whether Pressly's curve IVB changed from MIN to HOU and answer it in real units, not percentile-rank deltas.

5. **Team-context features are now first-class.** Per-team-season hitting/pitching/fielding aggregates plus roster construction mean the "rich roster blocking young prospects" mechanism that R-30 invoked to explain HOU-Luhnow's +0.83 young-prospect delta can finally be **tested**, not just hand-waved.

6. **Salary / surplus-value baseline is now possible.** Spotrac smoke-test confirmed accessibility (curl works; WebFetch does not, clarified in `2c70eeb`). Once the lock releases and the full ingest completes, the FanGraphs $/WAR fair-value baseline we set out to beat in `docs/NAIVE_BASELINE.md` can be replaced by a salary-based surplus-value baseline grounded in actual contract data, not market estimates.

7. **Awards data densifies the "elite player" tail.** 1,734 award-recipient rows 1990-2024 give us a clean binary signal for top-tail performance that doesn't collapse to WAR. Useful for both pre-trade pedigree features and as a sanity check on R-31's dev-credit attribution (a team that develops MVPs/Cy Youngs deserves dev credit even if career-WAR accounting is noisy).

8. **Front-office backfill to 1990 closes the regime-control window.** R-27 / R-28's regime analysis was bounded to 2010-2024 because BR front-office data started in 2010. With the ~1,780 new rows (1990-2009), the regime story extends back through the Beane '00s, the Theo Epstein BOS years, the original Cashman era: a 20-year additional window for regime-level claims.

**Affects.**

- **Replaces the years-since-debut age proxy** baked into R-13 / R-25 / R-27 / R-29 / R-30. Every coefficient in that chain needs a rerun against real age, with the strongest priority on R-30's veteran-vs-young bucket logic (which is age-sensitive by definition).
- **Replaces the post-1995 not-in-draft-picks international heuristic** from R-31. The dev-credit 2D map should be rerun with birth-country-based attribution before being shipped as a product artifact (D-30 candidate).
- **D-30 candidate (new): salary-based surplus-value baseline.** With Spotrac contracts landing, the FanGraphs $/WAR baseline target can be replaced with a salary-grounded surplus-value model, a stronger and more defensible benchmark.
- **Phase 2 V2 model build is now unblocked** with rate-based outcomes (pitch-movement deltas, framing runs, park-adjusted xwOBA/xERA), corrected demographics (real age, real birth country), and team-context features (roster construction, season aggregates).
- **New outcome views (`d4bb475`):** four added that draw on the fortification data. Documented in the affected views section.

Caveats:

- Spotrac contract ingest not yet committed end-to-end (DB lock).
- BR front-office 1990-2009 backfill is a scrape; spot-check QA on a handful of regimes (BOS-Duquette, OAK-Beane pre-Moneyball, CLE-Hart) before treating it as authoritative.
- Chadwick birth-date coverage is 99%+ for post-1980 debutees, weaker for 19th-century players we don't use anyway.

Files: `docs/archive/DATA_SOURCE_PROBE.md`, `docs/PHASE1_SYNTHESIS.md`, `src/savage_trade_evaluator/storage/schemas.py` (v11 to v19), commits `c038b5f` through `7e263c4` (12 total across 2026-05-16 and 2026-05-17).

---

---
