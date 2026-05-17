# Savage Trade Evaluator — Phase 1 Synthesis

**Status as of 2026-05-16.** This document consolidates the R-06 through R-31 research arc into a single readable narrative. It is the project's "where we are" reference point before any Phase 2 (product build) work begins.

---

## Executive summary

The project started with one specific thesis: **the Dodgers' MLB-leading dev system inflates prospects who then fail elsewhere ("system tax").** 32 rounds of testing produced a clean verdict on that thesis and a richer framework in its place.

**Five things you should know:**

1. **The original system-tax thesis is empirically rejected.** Across all 16 regimes tested, the YOUNG-PROSPECT bucket is *positive* in every single one — young players who get traded *gain* WAR after, regardless of which org they leave. No regime in V1 data shows the predicted pattern. (R-30, D-29)

2. **The Dodgers aren't anomalous.** They're #4 in dev, near-median in trade Δ. Top-tier on both axes, but not exceptional on either. The "elite system" reputation overstates them. (R-31)

3. **The strongest specific-regime finding is TEX-Jon Daniels' sell-high skill** — 9 vets traded with mean Δ -2.54 WAR (Lucroy, Minor, Michael Young, Darvish, Chirinos). Different mechanism than the original thesis but the cleanest single-person finding in the project. (R-29, R-30)

4. **The strongest pure-predictive finding is R-22's pitcher K%-trajectory coefficient** — mass=100%, mean -10.8 K-percentile-points, 90% CI [-17.1, -4.3]. Plain English: pitchers coming off K%-jump seasons regress hard post-trade. Largest credible coefficient in the entire ablation program. (R-22)

5. **The product-relevant artifact is the 2D org-quality map.** Each franchise gets a (dev WAR, trade Δ) coordinate. Quadrants identify strategic implications. HOU is unique in being HIGH-DEV / TRULY-POSITIVE-TRADE; SFG and SDP are bottom-quadrant on both axes. (R-31)

---

## The narrative arc

### Origin

Rob's framing: some MLB clubs function like college football programs. They install development advantages through analytics, tech, and coaching that elevate prospect production *while in-system*. Those prospects fail post-trade because the system advantage doesn't travel.

The Dodgers were the canonical example. The thesis predicted that LAD-departed prospects should systematically underperform their pedigree.

### Five methodological corrections, in order

Each correction emerged from a specific empirical surprise.

**1. Architectural correction — within-team variation (D-24).** Five rounds of feature engineering (R-06, R-07, R-09, R-14, R-15) all returned null results on WAR-based outcomes. Diagnosis: static team-level features (org dev-fit, per-coach record, draft pedigree, analytics cluster) cannot earn predictive keep against a multilevel model that already has team-cluster random intercepts. Features must vary *within* team to claim residual variance. R-15's first within-team-variation feature (acquired-player-quality) was directionally positive but still sub-threshold.

**2. Metric correction — rate-based outcomes (D-25, D-26).** R-16 ran the origin-org test using pitcher K% instead of WAR. Cross-metric replication revealed that R-12/R-13's WAR-based findings were partly artifactual — HOU/CLE/TBR/SDP all sign-flipped between metrics, while only HOU stayed consistent. R-19 then ran the R-15 ablation against an xwOBA outcome. **Three features became credibly real for the first time in the program** (mass >= 96%): acquired-player avg experience (-), war trajectory (-), and player quality (+). The same features on WAR-outcome were null. The outcome variable was hiding signal that rate-based outcomes surface.

**3. Regime correction — GM identity matters more than team identity (D-28).** R-25 split each team's trade history into decades and ran a multilevel with (team × decade) clusters. Variance decomposition: 90% within-team (regime/decade shifts), 33% between-team (org culture). GM regimes drive ~3× more variance than franchise identity. R-27 confirmed: when we replace team-clusters with regime-clusters, the WAR-based "LAD < HOU" pairwise weakens from 70% to 59%; the xwOBA-based version survives at 65%.

**4. Mechanism correction — sell-high vs system-tax are not the same thing (D-29).** R-29 archaeology on TEX-Daniels showed his negative regime is driven entirely by veterans at peak (Lucroy, Minor, Young, Darvish) — sell-high mechanic. R-30 decomposed every regime's trades into vet-at-peak vs young-prospect buckets. **The YOUNG-PROSPECT bucket is positive in every single regime tested**, including LAD-Friedman, HOU-Luhnow, OAK-Beane, MIL-Stearns. There is no regime in our data where the system-tax mechanism is credibly present.

**5. Coverage correction — dev credit is not trade Δ (D-30 candidate).** Rob noted that trade-outcome metrics don't credit teams for developing players who eventually became stars elsewhere. R-31 built a separate dev-credit attribution from `draft_picks` + first-MLB-team. Three iterations (raw → debuted-with-drafter filter → franchise-aliases + international-proxy + scout-to-sign + 2D map). The final 2D coordinate map is the product-relevant artifact.

### Surviving findings

After all the corrections, three things survive at conventional credibility thresholds:

**Specific-regime finding (R-30):** TEX-Jon Daniels has a credible sell-high skill. 9 veterans traded with mean pre-WAR +3.96 and mean post-trade Δ -2.54. The pattern survives trimming the 3 worst and 3 best trades. Not driven by outliers.

**Specific-coefficient finding (R-22):** Pitcher K%-trajectory predicts post-trade K% decline. Mass=100%, mean -10.8 K-percentile-points, 90% CI [-17.1, -4.3]. The largest credible coefficient in the project. Mechanism: heavy regression-to-the-mean at the pitcher arsenal-trajectory level.

**Three rate-based-outcome features (R-19):** On the xwOBA-delta outcome with n=143:
- acquired_player_avg_experience: 99% negative mass — aging effect, cleanly captured
- acquired_player_avg_war_trajectory: 98% negative mass — momentum effect
- acquired_player_quality: 96% positive mass — talent carryover with RTM partially absorbed

**Specific-team observation (R-31):** Only HOU is HIGH-DEV / TRULY-POSITIVE-TRADE. Only STL is LOW-DEV / strongly-POSITIVE-TRADE (best trade Δ in baseball at +0.10). Only SFG is dead-last-on-both-axes. The 2D map cleanly characterizes franchise strategy without requiring a system-tax narrative.

---

## The 2D org-quality map

### Coordinates (1990+ debutees, current 30 franchises only)

DEV WAR = career WAR of MLB debutees who first played for this franchise (draft + international, franchise-history-aliased).
TRADE Δ = mean change in WAR of departed players from t-1 to t+1 (1990+ trades, regime-aliased).

| Rank | Team | Dev | Intl | Total | Trade Δ | Quadrant |
|---|---|---|---|---|---|---|
| 1 | CLE | 1353 | 401 | 1754 | -0.14 | HIGH-DEV / ABOVE-MEDIAN-TRADE |
| 2 | NYY | 1109 | 423 | 1532 | -0.07 | HIGH-DEV / ABOVE-MEDIAN-TRADE |
| **3** | **HOU** | **1224** | **304** | **1528** | **+0.05** | **HIGH-DEV / POS-TRADE (unique)** |
| 4 | LAD | 1198 | 310 | 1508 | -0.03 | HIGH-DEV / ABOVE-MEDIAN-TRADE |
| 5 | SEA | 1123 | 376 | 1499 | -0.19 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 6 | MIN | 1209 | 282 | 1491 | -0.18 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 7 | ATL | 1129 | 278 | 1406 | -0.20 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 8 | MIA | 981 | 343 | 1324 | -0.15 | HIGH-DEV / ABOVE-MEDIAN-TRADE |
| 9 | LAA | 1019 | 252 | 1271 | -0.16 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 10 | OAK | 1123 | 146 | 1269 | -0.26 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 11 | TOR | 1108 | 133 | 1240 | -0.14 | HIGH-DEV / ABOVE-MEDIAN-TRADE |
| 12 | WSN | 1019 | 220 | 1239 | -0.11 | HIGH-DEV / ABOVE-MEDIAN-TRADE |
| 13 | CHW | 992 | 227 | 1219 | -0.34 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 14 | TEX | 992 | 224 | 1216 | -0.27 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| 15 | BOS | 973 | 227 | 1200 | -0.22 | HIGH-DEV / BELOW-MEDIAN-TRADE |
| **16** | **STL** | **1102** | **98** | **1200** | **+0.10** | **LOW-DEV / STRONG-POS-TRADE (unique)** |
| 17 | NYM | 833 | 276 | 1109 | -0.22 | LOW-DEV / BELOW-MEDIAN-TRADE |
| 18 | PIT | 892 | 171 | 1063 | -0.10 | LOW-DEV / ABOVE-MEDIAN-TRADE |
| 19 | KCR | 846 | 119 | 964 | -0.03 | LOW-DEV / ABOVE-MEDIAN-TRADE |
| 20 | MIL | 807 | 136 | 943 | -0.14 | LOW-DEV / ABOVE-MEDIAN-TRADE |
| 21 | PHI | 799 | 127 | 926 | -0.08 | LOW-DEV / ABOVE-MEDIAN-TRADE |
| 22 | BAL | 809 | 113 | 922 | -0.19 | LOW-DEV / BELOW-MEDIAN-TRADE |
| 23 | DET | 753 | 146 | 899 | -0.05 | LOW-DEV / ABOVE-MEDIAN-TRADE |
| 24 | CHC | 707 | 173 | 880 | -0.17 | LOW-DEV / BELOW-MEDIAN-TRADE |
| 25 | TBR | 776 | 104 | 880 | -0.37 | LOW-DEV / WORST-TRADE-Δ |
| 26 | ARI | 732 | 137 | 869 | +0.05 | LOW-DEV / POS-TRADE |
| 27 | CIN | 715 | 152 | 868 | -0.20 | LOW-DEV / BELOW-MEDIAN-TRADE |
| 28 | COL | 744 | 119 | 863 | -0.12 | LOW-DEV / ABOVE-MEDIAN-TRADE |
| 29 | SDP | 691 | 118 | 809 | -0.24 | LOW-DEV / BELOW-MEDIAN-TRADE |
| **30** | **SFG** | **624** | **48** | **671** | **-0.35** | **WORST-DEV / WORST-TRADE-Δ (unique)** |

Medians: total dev = 1200; trade Δ = -0.157.

### Quadrant strategic implications

- **HIGH-DEV / POS-TRADE** (HOU): keep doing what you're doing.
- **HIGH-DEV / BELOW-MEDIAN-TRADE** (BOS, MIN, ATL, OAK, SEA, CHW, TEX, LAA): improve trade execution. You have the pipeline.
- **LOW-DEV / STRONG-POS-TRADE** (STL): continue compensating with trades but invest in dev.
- **LOW-DEV / BELOW-MEDIAN-TRADE** (SDP, SFG, NYM, TBR, CIN, CHC, BAL): systemic rebuild needed on both axes.

The two axes are roughly orthogonal. Being good at dev does not predict being good at trades.

---

## Confirmed vs rejected

### Confirmed by V1 data

- **TEX-Daniels has credible sell-high skill** (R-29, R-30).
- **Pitcher K%-trajectory predicts post-trade K% decline** (R-22; mass=100%).
- **Within-team-variation features beat static team features** in our multilevel architecture (D-24, validated by R-19).
- **Rate-based outcomes surface signal that WAR-outcomes hide** (D-26, R-19, R-22).
- **GM regimes explain ~3× more variance than team identity** in origin-org effects (R-25).
- **CLE has the best amateur+international dev pipeline** at 1754 WAR (R-31).
- **HOU is the only HIGH-DEV / POS-TRADE franchise** in the 2D map (R-31).
- **STL has the best trade-Δ in baseball** at +0.10 (R-31).

### Rejected by V1 data

- **The original Dodgers system-tax thesis** (R-30, D-29). No regime shows the predicted young-prospect-declines pattern.
- **The "analytics-leader cluster" as a coherent group** (R-16, D-23). HOU/TBR/SDP/BOS/CLE don't cluster — they split on every cross-metric replication.
- **Modern CLE as a dev-travels org** (R-27). Their R-12/R-17 positive signal was almost entirely a Shapiro-era (2000s) echo we couldn't isolate in regime-controlled data.
- **HOU-Luhnow as a "dev-installs-travel" story** (R-27, R-30). The clean Luhnow-specific WAR intercept is +0.005 (near zero); HOU's positive signal is "rich-roster surplus prospects thrived elsewhere," not Strom-coaching-traveled-with-them.
- **The R-17 LAD < HOU/CLE pairwise on WAR** (R-27). Weakened from 70% to 59% under regime control. The xwOBA version (65%) survives but is no longer the project's headline finding.

### Inconclusive

- **LAD-specific system-tax pattern.** Across four progressively-controlled tests (R-10 raw → R-10 high-cohort split → R-10 multilevel → R-13 pairwise → R-27 regime-controlled), LAD trends slightly negative but never credibly separable from zero. Best statement V1 supports: "LAD trends marginally below HOU/CLE on rate-based outcomes; cannot reject H0 at any sample size we can reach."
- **The Anthopoulos "sign flip"** (TOR positive, ATL negative). R-29 showed both regimes have 95% CIs crossing zero. Apparent flip is consistent with sampling variation at n=23-31.

---

## Honest limitations

1. **Statcast era is 2015+.** All credibly-real coefficient findings (R-19, R-22) live in a 10-year window with small per-regime samples (~5-15 trades for some regimes on rate-based outcomes). Posterior credibility is real but extrapolation outside the window is risky.

2. **Front-office data starts 2010.** Regime-control window is bounded to 2010-2024. Cleveland's 2000s-Shapiro dev-travels signal couldn't be isolated. Pre-2010 trades fall back to team-only clustering.

3. **International signing data is a proxy.** "Post-1995 MLB debutees not in draft_picks" captures most Latin/Asian amateur free agents but mis-includes some pre-1990 draftees and some independent-league signings.

4. **Career WAR is a counting stat.** Long-stable franchises accumulate more dev-WAR partly from continuity. "WAR per debutee" is the cleaner efficiency measure.

5. **Trade Δ uses raw WAR change, not pedigree-controlled residual.** Mixed with aging curves and PT recovery; the bucket decomposition (R-30) is the right way to interpret per-regime trade Δ.

6. **15-feature matched-subset hits a wall around n=20-25** on the rate-based outcomes. Further feature additions need either imputation, missing-indicator features, or outcome-specific feature subsets.

7. **bWAR vs fWAR inter-system disagreement is real** and roughly the same magnitude as the per-regime effects we're measuring. We chose bWAR (D-11) but a robustness check on fWAR was never run.

---

## Lessons for Phase 2

1. **Default to rate-based outcomes** (xwOBA, K%, xERA, era_plus) for any research-thread test. WAR is preserved only for the surplus-value baseline (product convention). Codified in D-26.

2. **Cluster on (team, GM-regime), not just team** in any model that spans multiple decades. Codified in D-28.

3. **Within-team-variation features beat static team features** in multilevel models with team-cluster random intercepts. Codified in D-24.

4. **Credibility threshold = 90% CI excludes zero AND directional mass >= 95%**, not CRPS movement. Sample-size limitations on rate-based outcomes mean test-set CRPS is unreliable below n=100. Codified in D-26.

5. **Per-regime claims must replicate across two+ outcome metrics** to count as confirmed. Codified in D-25.

6. **Per-regime intercepts must be decomposed into sell-high vs system-tax buckets** to interpret the mechanism. Codified in D-29.

7. **Ship the 2D org-quality coordinate** as a first-class artifact in the V2 product. Each org gets a (dev, trade) tuple with quadrant label and strategy implications. (D-30 candidate.)

---

## Open follow-ups (deferred to Phase 2 or beyond)

- **Build a sell-high-detection feature** for the V2 model based on TEX-Daniels' archetype.
- **Re-ablate all five "WAR-null" features (R-06/07/09/14)** against rate-based outcomes. Several may be credible on xwOBA / K% / xERA.
- **Scrape MLB Trade Rumors / Baseball America international signing trackers** via Playwright. Cleaner int'l attribution than the post-1995-not-in-draft-picks proxy.
- **Build the (team, regime)-cluster multilevel framework** as the standard V2 architecture.
- **Rate-based-surplus naive baseline** (xwoba_received - xwoba_given_up) as the V2 model target. The current WAR-surplus baseline is contaminated by D-26 issues.
- **Cross-metric replicate R-22's k_trajectory finding under regime clustering.** The largest credible coefficient in the project hasn't been retested with regime-aware intercepts.
- **Per-pitch-type dev-fit analysis** using the new statcast_pitcher_arsenal_stats table (R-26). Tests whether HOU's curveball install / LAD's sweeper install patterns are pitch-specific.

---

## Files of record

- `RESEARCH_LOG.md` — full chronological R-01 through R-31 log with reproducibility details.
- `~/Vault/savage_vault/wiki/trade-eval--decisions.md` — D-01 through D-29 modeling/scope decisions.
- `scripts/` — 17 standalone scripts for each round's analysis, all runnable.
- `src/savage_trade_evaluator/` — V1 data spine + model code.
- `data/duckdb/trades.db` — DuckDB store with all ingested data.

This document is the synthesis index. Read it first for the narrative; reach into the research log for any specific result's setup, sample size, and reproducibility detail.
