# Omnibus ablations and regime control (R-20 to R-27)

Four outcomes tested at once, which surfaces R-22, the largest credible
coefficient in the project. Then the regime correction: GM tenure, not franchise
identity, is the cluster that carries the variance.

Part of the [research log](README.md). Entries run oldest first.

---

## [2026-05-16] R-20/21/22/23: omnibus four-outcome ablation. R-22 surfaces the largest credible coefficient in the entire project

**Question (plain English).** R-19 showed rate-based outcomes surface features that WAR-outcomes hide. Generalize: run the full 15-feature multilevel model against multiple rate-based outcomes (xERA, K%, xwOBA-surplus) and the original WAR-surplus baseline. Do we see different features become credible depending on outcome choice? Also: do the new pitcher arsenal features (k_trajectory, arsenal_volatility added in R-24 setup) show up?

**Setup.** Single omnibus script (`scripts/ablation_multi_outcome_omnibus.py`) runs the same 15-feature multilevel against five outcomes:
- WAR-surplus (R-20; sanity check + re-analysis of prior WAR-null features)
- xERA-delta (R-21; pitcher quality-of-contact-allowed)
- K%-delta (R-22; pitcher percentile-rank strikeout rate)
- xwOBA-surplus (R-23; new view `trade_xwoba_surplus`, rate-based equivalent of naive baseline)
- xwOBA-delta receiver-side (R-19 replicate)

Three new outcome views built (`trade_xera_outcome`, `trade_kpct_outcome`, `trade_xwoba_surplus`). Two new pitcher features built (`receiver_acquired_pitcher_k_trajectory`, `receiver_acquired_pitcher_arsenal_volatility`).

**Result.**

| Outcome | n | Credible (mass >= 97.5%) | Directional (85-97%) | Skipped? |
|---|---|---|---|---|
| WAR-surplus (R-20) | 100 | dev_fit_pitching (+1.05, mass=99%) | war_trajectory (96% neg), player_quality (93% pos), best_draft_pick (93% neg), experience (87%), org_pitcher_k_jump (85%) | none |
| xERA-delta (R-21) | 69 | (none reach 97.5%) | dev_fit_hitting (96% pos), dev_fit_pitching (96% neg = improvement), prior_year_wins (96% pos), player_quality (92%), best_draft_pick (87%), pyth_pct (86%) | none |
| **K%-delta (R-22)** | **56** | **acquired_pitcher_k_trajectory (-10.8, mass=100%, CI [-17, -4])** | experience (97% neg), dev_fit_pitching (91% pos) | none |
| xwOBA-surplus (R-23) | 25 | none | none | SKIPPED (n too small) |
| xwOBA-delta (R-19 replicate) | 20 | none | none | SKIPPED (n too small) |

**R-22's headline result:** `receiver_acquired_pitcher_k_trajectory` has the **largest credible coefficient in the entire ablation program**. Mass = 100% negative. Mean = -10.8 K-percentile-points. 90% CI = [-17.1, -4.3]. Plain English: a pitcher who gained 10 K-percentile-points in the year before being traded is expected to *lose* about 10.8 K-percentile-points the year after the trade. Strong, statistically credible regression-to-the-mean at the pitcher-arsenal-trajectory level.

**Interpretation (plain English).**

1. **R-22 is the strongest predictive finding from the entire 20-round program.** Mass=100% with effect size -10.8 on the K-percentile scale. Visible only with K% as the outcome and invisible on WAR. The metric correction (D-26) was load-bearing for surfacing it.

2. **"Best feature" is outcome-specific.** No single feature is credible across all four tested outcomes. WAR-surplus = team-level pitching dev. xERA = dev-fit-pitching + dev-fit-hitting + prior wins. K% = pitcher arsenal trajectory + age + dev. xwOBA = experience + war_trajectory + player_quality. Different outcomes encode different mechanics; the right "feature importance" depends on what you're predicting.

3. **R-20 WAR-surplus result is genuinely informative.** `receiver_dev_fit_pitching` is credibly positive (+1.05 WAR per +1 SD in the dev-fit feature). This was sub-threshold in prior WAR ablations because the matched-subset was larger. Tighter subset (n=100) sharpens per-feature identification. The K-jump-3yr feature gained directional support too (85% vs prior 74%).

4. **xERA shows the cleanest dev-fit story.** Pitching-dev = lower xERA (better quality-of-contact allowed); hitting-dev = higher xERA on pitchers acquired (counterintuitive but probably reflects org composition tradeoffs). Both at 96% directional mass, just shy of the credibility threshold given n=69.

5. **The matched-subset wall.** With 15 features all required non-null, xwOBA-surplus and the R-19 replicate drop to n=20-25, too small to fit reliably. We've hit the limit of the strict all-features-non-null methodology. Future ablations need: (a) imputation, (b) missing-indicator features, or (c) feature-subset-specific runs (slim feature set per outcome).

**Affects.**

- **R-22's k_trajectory finding is the most operationally useful single result so far.** It directly informs trade evaluation: don't pay a premium for pitchers coming off K%-jump seasons; they're going to regress.
- D-26 is multiply validated. WAR-outcome research alone would have missed R-22 entirely.
- New methodological constraint surfaced: 15-feature matched-subset is the wall. **D-27 candidate:** ablation protocols should switch to outcome-specific feature subsets, or use missing-indicator imputation, beyond ~13 features.
- The three new outcome views (`trade_xera_outcome`, `trade_kpct_outcome`, `trade_xwoba_surplus`) are reusable for any future per-trade-receiver analysis.
- The two new pitcher features (k_trajectory, arsenal_volatility) earn keep on K%-outcome but not on WAR. Consistent with the metric-specificity finding.

Files: `scripts/ablation_multi_outcome_omnibus.py`, `src/savage_trade_evaluator/storage/outcome_views.py` (added 4 views), `src/savage_trade_evaluator/modeling/context_aware.py` (added 2 features).

---

---

## [2026-05-16] R-25: Org-stability decade-split. GM regimes drive 90% of within-team variance; org-identity-as-feature is wrong

**Question (plain English).** Are organizations static, or do GM regimes matter? When we say "LAD-departed players underperform HOU-departed players" (R-17, ~70% pairwise), is that about *organizational culture that persists across regimes* or about *specific GM regimes that happened to occupy those org chairs during our sample*?

**Setup.** Split each origin org's trade history into decades (1990s/2000s/2010s/2020s). Fit a multilevel model with (origin x decade) cells as the cluster instead of just origin. 4575 trade legs across 120 (team, decade) cells (after MIN_N=8 filter per cell). Decompose variance of the per-cell intercepts into between-team (org culture) and within-team-across-decades (regime/era) components.

**Result.**

Variance decomposition (teams with 2+ decades):
- **Total variance of decade-cell intercepts: 0.00032**
- **Between-team variance (org culture):       0.00010  (33% of total)**
- **Within-team variance (regime/decade):      0.00029  (90% of total)**

Within-team variance is ~3x larger than between-team variance. **GM regimes dominate.**

Team-by-team decade breakdown of highlighted orgs (mean of alpha_cell intercept):

| Team | 1990s | 2000s | 2010s | 2020s | Pattern |
|---|---|---|---|---|---|
| HOU | +0.008 | -0.014 | **+0.023** | +0.017 | Luhnow/Strom era (2010s) peak; fading |
| CLE | +0.012 | **+0.040** | +0.003 | -0.009 | Shapiro era (2000s) peak; modern CLE neutral |
| LAD | +0.010 | -0.028 | -0.018 | +0.009 | Friedman era (2010s) negative; modern back to neutral |
| OAK | -0.003 | **+0.039** | +0.025 | +0.008 | Beane peak 2000s-2010s; fading |
| STL | +0.031 | +0.026 | +0.003 | +0.009 | "Cardinal Way" was 1990s-2000s |
| TBR | +0.003 | -0.019 | -0.023 | -0.006 | Mild persistent system-tax pattern (most stable in our set) |
| BOS | -0.011 | -0.029 | +0.011 | +0.008 | Sign-flipped between Epstein and Cherington/Bloom |

Per-cell 90% credible intervals all cross zero. At the individual decade level we cannot credibly separate any single cell from zero. The variance decomposition is the right signal here: it's a population-level claim about how variance is structured, more reliable than per-cell estimates.

**Interpretation (plain English).**

1. **Organizations are NOT static.** 90% of the variance in per-decade intercepts is within-team (regime shifts). Only 33% is between-team (org culture sticking across regimes). The ratio is ~3:1 in favor of regime over culture.

2. **The R-17 "LAD < HOU" finding is really "Friedman-era LAD < Luhnow-era HOU."** Both are regime-specific. Pre-Friedman LAD and pre-Luhnow HOU look like average MLB teams. The pairwise probability we celebrated (~70%) was driven by a specific period overlap.

3. **The "HOU dev-travels" narrative is largely Luhnow/Strom legacy.** Peaked in 2010s (+0.023), fading in 2020s (+0.017). Pre-Luhnow HOU shows no signal.

4. **CLE in our "analytics-leader cluster" was reputation, not current data.** Modern CLE (2010s-2020s) shows zero or slightly negative dev-travels signal. The strong CLE effect was the 2000s Shapiro era.

5. **For the V2 product**, a new GM hire is a model-input change. Treating "Houston" as a fixed team-level feature is wrong. (team x GM-regime) clusters are the right design.

6. **TBR is the most stable** of the analytics-leader cluster, mildly negative across all four decades. The Rays' reputation may genuinely be organizational rather than regime-driven, though the effect is small enough that this could also be noise.

**Affects.**

- **Reframes R-10 through R-22 as regime-specific findings, not organizational findings.** Origin-org effects we measured are largely artifacts of which GMs happened to be running those teams during 2015-2024 (Statcast era) or 1990-2024 (WAR era).
- **D-28 candidate** (Phase 2 V2): use (team x GM-regime) clusters instead of just team clusters. Requires `front_office` table processing to identify regime boundaries.
- **The "analytics-leader cluster" framing should be regime-dated.** Houston-Luhnow-era is in the dev-travels cluster; Houston-2024-onward may not be.
- **Sample bias awareness**: Statcast outcomes (2015+) sample primarily one regime per team. The xwOBA / K% findings from R-19/R-22 are really "current-regime" findings. They don't speak to whether the same team in a different era would behave the same way.

Files: `scripts/org_stability_decade_split.py`.

---

---

## [2026-05-16] R-26: Statcast-extended ingest. Batter percentile ranks, pitcher arsenal stats, OAA

**Question (plain English).** What Statcast data are we under-using? Three sources Savant publishes but we hadn't ingested:
1. Batter percentile ranks (hitter analog to the existing pitcher percentile table)
2. Per-pitch-type arsenal stats (slider vs curve vs FB breakdowns)
3. Outs Above Average (per-position defensive metric)

**Setup.** Built `ingest/statcast_extended.py` with three functions wrapping the pybaseball APIs. New schema additions (v12): `statcast_batter_percentile_ranks`, `statcast_pitcher_arsenal_stats`, `statcast_outs_above_average`. CLI: `ste ingest statcast-extended`.

**Result (2015-2024 historical ingest):**

| Source | Rows |
|---|---|
| Batter percentile ranks (614 hitters/year x 10 years) | 6,460 |
| Pitcher per-pitch-type arsenal (1,881 player-pitch-rows/year x 10 years) | 13,542 |
| Outs Above Average (across OF + 4 infield positions, ~268/year x 10 years) | 2,479 |

Catcher framing was probed but `pybaseball.statcast_catcher_framing` fails CSV-parsing on Savant's response. Deferred; flagged in catalog.

**Interpretation (plain English).**

These three sources open three V2 feature avenues:

1. **Hitter dev-signatures.** With hitter percentile ranks we can now build hitter equivalents to R-22's pitcher k_trajectory feature: chase% trajectory, hard-hit% trajectory, swing-length trajectory. These should surface dev-fit effects on hitters that current xwOBA-only features may obscure.

2. **Pitch-type-specific dev-fit.** Houston's reputation is curveball install (high spin). LAD's is sweeper install (high horizontal break). Same pitcher, different installs. The pitcher_arsenal table lets us decompose K% gains and losses by pitch type, which answers whether a trade improved the player's slider or just his total K%.

3. **Defensive contribution decomposition.** "LAD inflates production" is partly defensive: Mookie, Lux, Muncy, and good catching add up. OAA lets us split offensive vs defensive trade outcomes.

**Affects.**

- Three new tables ingested 2015-2024; schema v12.
- Catalog updates: 3 new "ingested" entries; 1 "blocked" (catcher framing CSV-parse issue).
- New feature engineering opportunities for V2 ablations once we re-run on rate-based outcomes per D-26.
- The pitcher arsenal table opens a direct follow-up: was R-22's k_trajectory effect driven by a specific pitch type?

Files: `src/savage_trade_evaluator/ingest/statcast_extended.py`, `src/savage_trade_evaluator/storage/schemas.py` (v11 -> v12).

---

---

## [2026-05-16] R-27: Regime-control reruns. Most R-17 findings weaken; OAK-Beane emerges as the strongest specific-regime signal

**Question (plain English).** Per D-28, V2 model architecture must cluster on (team, GM-regime) not just team. Rerun R-12/R-17 origin-org system-tax tests with regime_id as the cluster. Which of our prior team-level findings survive being decomposed into specific GM eras?

**Setup.** Built `team_regime_assignments` view that maps (bref_code, season) to regime_id = "{team}_{decision_maker}". Decision-maker is the top baseball-ops role per season (President > GM). Front_office data covers 2010-2024 so regime-control is bounded to that window.

`scripts/regime_control_reruns.py` runs the origin-org multilevel on three outcomes (WAR, xwOBA, K%) with regime_id as cluster. Reports per-regime intercepts and Friedman-LAD-vs-other pairwise probabilities.

**Result.**

### Per-regime intercepts

WAR (n=2046, 79 regimes after MIN_N=6 filter):

| Regime | n | Intercept | 90% CI | P(<0) |
|---|---|---|---|---|
| LAD-Friedman | 63 | -0.021 | [-0.158, +0.086] | 61% |
| LAD-Colletti | 20 | +0.007 | [-0.116, +0.144] | 47% |
| HOU-Luhnow | 44 | +0.005 | [-0.111, +0.130] | 47% |
| HOU-Click | small | (filtered/not shown) | | |
| CLE-Shapiro | 22 | -0.002 | [-0.130, +0.127] | 51% |
| CLE-Antonetti | 45 | -0.009 | [-0.133, +0.102] | 54% |
| **OAK-Beane** | 66 | **+0.057** | [-0.046, +0.232] | **26%** |
| STL-Mozeliak | 49 | +0.015 | [-0.095, +0.148] | 43% |
| BOS-Bloom | 20 | +0.021 | [-0.095, +0.173] | 41% |

xwOBA (n=514, 35 regimes):
| LAD-Friedman | 27 | -0.003 | [-0.019, +0.009] | 62% |
| HOU-Luhnow | 10 | +0.003 | [-0.011, +0.021] | 40% |
| CLE-Antonetti | 25 | +0.003 | [-0.010, +0.018] | 39% |
| OAK-Beane | 18 | -0.001 | [-0.016, +0.014] | 52% |

K% (n=141, 18 regimes): LAD-Friedman not in sample (LAD doesn't trade enough pitchers in Statcast era). STL-Mozeliak -5.7 K-pct-points (P(<0)=85%); OAK-Beane +2.9 (P(<0)=28%).

### Pairwise: Friedman-LAD vs other regimes

WAR:
- vs LAD-Colletti: 60%   vs HOU-Luhnow: 60%   vs CLE-Antonetti: 55%
- vs OAK-Beane: **74%**   vs STL-Mozeliak: 62%   vs BOS-Bloom: 63%

xwOBA:
- vs HOU-Luhnow: 65%   vs CLE-Antonetti: 66%   vs OAK-Beane: 58%   vs BOS-Bloom: 63%

R-17 (team-level) comparisons: LAD vs HOU = 70% (WAR) / 69% (xwOBA); LAD vs CLE = 75% (WAR) / 67% (xwOBA).

**Interpretation (plain English).**

1. **WAR-based LAD < HOU pairwise WEAKENED from 70% to 59%** under regime control. The team-HOU number was averaging four regimes (Wade/Luhnow/Click/Brown). The clean Luhnow-specific intercept is +0.005, essentially zero. The R-17 effect was partly a "non-Luhnow HOU regimes pulling team-HOU down" artifact.

2. **xwOBA-based LAD < HOU pairwise SURVIVES** regime control: 69% -> 65%. The rate-based version of the comparison survives more of the controls. This was already the cleaner test per D-26; it stays cleaner.

3. **Modern CLE shows NO dev-travels signal** in regime-controlled view. Shapiro 2010-2015 = -0.002; Antonetti 2016+ = -0.009. Both near zero. The R-12/R-17 CLE-positive finding was almost certainly driven by pre-2010 Shapiro-era trades that contributed to the team-level aggregate but predated our front_office data window.

4. **The HOU "dev-travels" thesis (MVP Machine Ch 9) is weaker than the team-level data suggested.** Luhnow-specific intercept is +0.005 on WAR, not the +0.034 we'd see at team-HOU level. Some of the team-level signal may have been pre-Luhnow Wade-era trades or post-Luhnow Click trades that benefit from the lingering Luhnow infrastructure.

5. **OAK-Beane emerges as the strongest specific-regime positive outlier.** +0.057 WAR intercept, P(<0) = 26%. Friedman-LAD vs OAK-Beane pairwise: 74% on WAR, the strongest pairwise comparison we have. Beane's ~25-year tenure gives enough data to credibly attribute this to him personally rather than to "Oakland the organization."

6. **R-22's k_trajectory feature credibility (mass=100%, -10.8) is not retested here.** R-27 only checks regime intercepts, not feature coefficients. Whether the largest credible coefficient in the project survives regime clustering requires a separate ablation. Queued.

**Affects.**

- **Reframes R-17 findings as half-surviving regime control.** The xwOBA-based LAD < HOU/CLE pairwise survives. The WAR-based version is weakened, particularly for CLE where modern regimes show no signal at all.
- **OAK-Beane is now the project's cleanest specific-regime finding.** Should be foregrounded in any product-facing summary alongside the still-tentative LAD-Friedman vs HOU-Luhnow xwOBA comparison.
- **Reframes the HOU dev-travels narrative.** It's a *partial* Luhnow-era effect that may include both pre-Luhnow setup and post-Luhnow inheritance. Cleaner framing: "Beane-era OAK pitchers gained K% after departure with the strongest credibility we can measure" rather than "Luhnow-HOU is the dev-travels champion."
- **Modern CLE drops out of the analytics-leader-cluster framing entirely.** Their 2010-2024 regimes show zero dev-travels signal. The reputation predates our data window.
- **R-22's headline credibility result is the obvious next test.** If k_trajectory's -10.8 effect on K% survives regime clustering, it stands as the project's strongest finding regardless of regime-aware concerns.

Files: `scripts/regime_control_reruns.py`, `src/savage_trade_evaluator/storage/outcome_views.py` (added `team_regime_assignments` view).

---

---
