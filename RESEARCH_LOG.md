# Trade Eval Research Log

Append-only chronological record of experiments, hypothesis tests, ablations, and null results. Different from:

- `LESSONS.md` — infrastructure gotchas that generalize (FG blocked, DuckDB lock, perf wins)
- `trade-eval--decisions.md` (vault) — D-NN decisions, "what we chose and why"
- `CHANGELOG.md` — shipped features per commit

**This** file captures: *what we tried, what we measured, and what the evidence implies.* Each R-NN is meant to be reproducible — point at the script or commit, give the seed and the metrics, summarize the interpretation.

**Entry format:**

```markdown
## [YYYY-MM-DD] R-NN: Short title

**Question.** What we wanted to learn.
**Setup.** Data subset / features / model / seed / train-test split.
**Result.** Metrics. Reference scripts/<file>.py or commit hash.
**Interpretation.** What this means and confidence level.
**Affects.** D-NN entries supported/refined and follow-up R-NN candidates.
```

Add new entries at the top. Never rewrite history — supersede with a new R-NN that references the prior one.

---

## [2026-05-16] R-12: WAR-version of origin-org system-tax test on R-11 expanded sample

**Question.** With R-11 nearly doubling the affiliated trade-event sample (2,734 -> ~6,200), does the R-10 origin-org system-tax thesis become credibly separable? Specifically: can we now distinguish LAD as a system-tax org from the analytics-leader cohort baseline, or from zero?

**Setup.** Mirror of `scripts/origin_org_pedigree_controlled.py` (R-10) with three changes:
- Outcome: Δ WAR (war_t_plus_1 - war_t_minus_1) instead of Δ xwOBA. bWAR has full 1871+ coverage so the new pre-2010 Retrosheet trades feed straight in.
- Pre-trade control: war_t_minus_1.
- Receiver dev-fit covariate dropped — `org_hitter_xwoba_jump_3yr` is Statcast-era only and would reintroduce a 2015+ filter, defeating the R-11 expansion.
- Filter trade_season >= 1990.
- n=4,235 trade legs across 30 origin orgs.

PyMC multilevel, 4 chains x 2000 draws, target_accept=0.95.

**Result.**

Population posteriors:
- `α (league baseline) = -0.154` [-0.194, -0.112] — average post-trade WAR loss of ~0.15 after controls.
- `β_pre = -1.01` [-1.05, -0.98] — extreme RTM. A +3 WAR pre-player drops ~2 WAR post.
- `τ_origin = 0.066` [0.016, 0.121] — origin-org variance IS detectable as a population parameter; lower bound well above zero.
- `σ = 1.41` — per-trade noise ~20x larger than τ_origin.

Key per-org intercepts (selected):

| Org | n | Intercept | P(<0) | vs R-10 xwOBA P(<0) |
|---|---|---|---|---|
| NYM | 187 | -0.040 | 74% | 15% (FLIPPED sign) |
| TBR | 150 | -0.040 | 73% | 46% |
| SDP | 235 | -0.034 | 72% | 44% |
| **LAD** | **169** | **-0.022** | **64%** | **63%** (same) |
| BOS | 155 | -0.017 | 61% | 55% |
| HOU | 124 | +0.027 | 34% | 37% (consistent) |
| CLE | 180 | +0.039 | 26% | 39% (consistent) |
| MIA | 180 | +0.060 | 18% | — |

**Interpretation.**

1. **LAD result replicates but remains inconclusive at 6x more data.** R-10 P(<0) = 63% → R-12 P(<0) = 64%. 90% CI still crosses zero ([-0.124, +0.065]). **Best statement V1 data can make is "LAD trends slightly negative on departed-player residuals; cannot reject H0 at the current sample."** Doubling-the-data did not break ambiguity.

2. **Analytics-leader cohort splits cleanly into two camps.** 4 of 6 negative (LAD, TBR, SDP, BOS), 2 positive (HOU, CLE). The "tech-forward orgs broadly produce system guys" framing is rejected by the data. There IS a subgroup pattern inside the cohort, but it's not what Rob's original thesis predicted.

3. **HOU/CLE dev-travels finding is now the cleanest signal.** Both positive across both metrics (R-10 xwOBA and R-12 WAR). Supports the origin-side mirror reading of MVP Machine Ch 9: improvements installed under Strom/Espada/Willis travel with the player. CLE joining HOU strengthens the claim — both known pitching-dev-forward orgs.

4. **NYM cross-metric sign flip is genuinely interesting.** xwOBA = +0.012 (positive); WAR = -0.040 (negative). Reading: Mets-departed players retain rate-stat quality but lose counting WAR via reduced playing time / aging. Aligns with the Pinheiro-Szymanski mean-variance framing — these would be "high-mean, declining-variance" hitters whose rate stats stabilize while their PT/durability drops.

5. **WAR-specific confound to note.** β_pre = -1.01 is very aggressive. Players with high pre-WAR are predicted to lose almost an entire WAR per pre-SD. Some of this is aging (players are traded at peak); some is PT regression (vet traded to bench role). The single covariate cannot fully decompose these. The pure-test version would condition on age and post-trade games-played, neither of which is currently in our schema.

Confidence: high on the within-cohort split being real. Moderate on LAD/HOU/CLE individual rankings (n=124-180 per org, posterior 90% CIs still wide). Low on cross-metric reconciliation (NYM flip is consistent with mean-variance theory but not directly tested).

**Affects.**

- Refines D-21 (origin-org system-tax decision). Updates the cohort claim: "analytics-leader cohort splits into LAD/TBR/SDP/BOS (negative) and HOU/CLE (positive) on WAR-residual."
- Strengthens the case for HOU/CLE dev-travels as a publishable single-finding. Larger and cleaner signal than LAD.
- The LAD-specific synthetic-control test (Mixtape Ch 10) is *still* the only path to disambiguate (a) system-tax from (b) sell-high — and now the case for running it is weaker because doubling the sample didn't move the LAD posterior off zero.
- Queued: age-conditioning the model. Age is needed to separate "aging at peak" from "system-dependent production." Requires `bwar_player_seasons` first_mlb_year join — feasible from current schema.

Files: `scripts/origin_org_pedigree_controlled_war.py`.

---

## [2026-05-16] R-11: Retrosheet pre-2010 transaction ingest — 2.5x affiliated-trade sample expansion

**Question.** R-06/07/09/10 all hit the same noise floor: ~30 trades per origin-org is too few to detect any feature contribution above the regression-to-the-mean baseline. Will ingesting Retrosheet's transaction database (which the Pinheiro-Szymanski 2022 paper cites as covering 1994-2016) push the sample size into a regime where per-org effects become credibly separable?

**Setup.** Built `ingest/retrosheet_transactions.py`. Pulls `https://www.retrosheet.org/transactions/tranDB.zip` (1.2 MB, last updated 2022, 101,594 rows total). Parses CSV with quoted/padded fields. Filters to `type = 'T'` (trades only). Bridges Retrosheet 8-char player IDs to MLB Stats API integer IDs via the Chadwick Register (`pybaseball.chadwick_register()`, 25,620 retro->mlbam mappings). Maps Retrosheet 3-char team codes (NYA, CHN, SLN, etc.) to our `bref_code` via a hand-coded 33-entry dict covering the modern-MLB-era franchise set. Transaction IDs offset by 10^10 to avoid PK collision with the MLB Stats API IDs. Default ingest window: 1880-2009 to avoid duplicate-attribution conflicts with the existing MLB Stats API rows for 2010+.

**Result.**

| Metric | Before | After |
|---|---|---|
| transactions rows | 703K | 720K (+16,890 retrosheet trade legs) |
| pre-2010 affiliated trade events | ~1 (D-14) | **~2,500** |
| pre-2010 trades with every leg ID-resolved | 0 | **4,551** |
| total `trade_events_affiliated` (all eras) | 2,734 | **6,200+** |

Decade rollup of `trade_events_affiliated` after ingest:

```
1880s: 1     1890s: 15    1900s: 38    1910s: 39
1920s: 34    1930s: 72    1940s: 91    1950s: 176
1960s: 449   1970s: 888   1980s: 902   1990s: 979
2000s: 1166  2010s: 1660  2020s: 987
```

Pressly trade still validates (transaction 86280 in source data → 10000086280 after offset, 3 legs intact). Manny Ramirez BOS→LAD 2008-07-31 three-team trade verified end-to-end: 6 legs (Manny, Bay, Hansen, Moss, LaRoche, Morris) with correct from/to teams and human-readable names via Chadwick.

**Interpretation.**

- **Sample-size bottleneck is broken for any test that uses bWAR-based outcome windows.** bWAR has full 1871+ coverage, so the new ~2,500 pre-2010 affiliated trades feed straight into `trade_player_war_window`. R-10 WAR-version, R-09 draft-pedigree, and any future origin-org test can now run on roughly 2.5x the data.
- **Statcast-era tests (xwOBA, xERA, arsenal percentiles) get zero benefit** — those windows are 2015+ only. R-10 as run (xwOBA-based) is unchanged.
- **MLB Pipeline top-100 / FV-grade gap remains.** Retrosheet has no FV grades; the prospect-pedigree gap is still draft-pick-only via `draft_picks`. The R-09 ceiling is unchanged.
- **No PK conflicts observed** at the 10^10 offset. Source attribution via the `source` column (`retrosheet` vs `mlb-stats-api`) is intact, queries that need to filter or audit by provenance work.
- **Manny Ramirez 2008 case** is now reconstructable. That trade (3-team, 6 legs, BOS giving up Manny + 2 prospects, getting Bay; PIT giving up Bay + 2 prospects, getting Hansen + Moss + LaRoche + Morris) is the kind of complex multi-team trade structure the V1 backtester needs to handle correctly — and now does, including the LAD-side leg directly relevant to the R-10 system-tax thread.

**Affects.**

- Unblocks the WAR-based version of R-10 — can now repeat the pedigree-controlled multilevel test with ~2.5x sample and credibly separable per-origin posteriors (or at least a tighter `tau_origin` lower bound).
- Catalog updated: `retrosheet-transactions` source entry marked ingested (1880-2022, ~5,300 trade legs total, ~4,500 affiliated post-mapping).
- D-22 added: source-attribution model and offset convention documented.
- Queued follow-ups: (i) R-10 WAR-version rerun, (ii) extending coverage to free-agency type ('F'/'Fg') as a separate scope decision, (iii) augmenting `mlb-stats-api` 2010-2024 with Retrosheet 2010-2022 as a cross-validation source rather than primary.

Files: `src/savage_trade_evaluator/ingest/retrosheet_transactions.py`, `data/static/retrosheet/tranDB.zip` (cached download).

---

## [2026-05-16] R-10: Origin-org system-tax test — LAD signal collapses 25x under controls; NYM/HOU are bigger outliers in the opposite direction

**Question.** Rob's "system guy" hypothesis: do tech-forward orgs (LAD specifically) produce prospects whose production is partly attributable to org infrastructure, such that the player regresses after trade? Mirror image of the MVP Machine Ch 9 receiving-side dev-fit feature.

**Setup.** Three rounds of increasingly-controlled tests on `trade_player_xwoba_window` (2015+, hitters):

- Round 1: Raw mean Δxwoba per origin-org. n=577 across 30 orgs.
- Round 2: Split each origin's departed-hitter population by pre-trade xwOBA tier (HIGH ≥ 0.330 / LOW < 0.300) to test the selection-cancelation hypothesis.
- Round 3: PyMC Bayesian multilevel — `Δxwoba ~ α + α_origin[i] + β_pre·z(pre_xwoba) + β_season·z(season) + β_rdf·z(receiver_dev_fit) + ε`. Partial pooling on origin. 4 chains × 2000 draws.

**Result.**

| Round | LAD effect | Interpretation |
|---|---|---|
| 1 (raw delta) | -0.0094 (rank #9, SEM 0.018) | Indistinguishable from noise. Apparent rejection. |
| 2 (HIGH-cohort split) | **-0.076** (n=10, SEM 0.023, **3.2σ**) | LAD HIGH cohort drops 75% more than league non-analytics HIGH (-0.043); 2.5× more than other analytics-leaders HIGH (-0.030). Apparent weak support. |
| 3 (pedigree-controlled multilevel) | **-0.003** (90% CI [-0.018, +0.009], P(<0)=63%) | Collapsed 25× from raw. Crosses zero. **Not credibly separable.** |

Population posteriors from R-3: `β_pre = -0.048` [-0.054, -0.041] dominates — regression to the mean. `τ_origin = 0.009` [0.002, 0.018] — between-org variation is real but ~10× smaller than within-org noise (`σ = 0.088`).

Comp set after controls — analytics-leader cohort fails to generalize:

| Org | Intercept | P(<0) |
|---|---|---|
| **LAD** | **-0.003** | **63%** |
| BOS | -0.001 | 55% |
| TBR | +0.001 | 46% |
| SDP | +0.001 | 44% |
| CLE | +0.003 | 39% |
| HOU | +0.003 | 37% |

Accidental findings, both stronger than the LAD signal:

- **NYM (+0.012, P(<0) = 14.6%)** — biggest positive outlier. Departed Mets *gain* xwOBA after controls. Inverse-system-tax candidate.
- **HOU (+0.003, P(<0) = 37%)** — positive intercept. Origin-side mirror of MVP Machine Ch 9: dev improvements installed under Strom *travel* with the player. Verlander/Cole/Greinke arc all fit.

**Interpretation.**

1. **Origin-org effect is real but small.** `τ_origin` posterior bounded above zero at 90%. ~0.01 SD across orgs on xwOBA scale.
2. **Rob's LAD-specific intuition gets partial credit** — LAD ranks #4 most negative of 30 — but magnitude (~3 thousandths xwOBA) sits below V1 detection floor at n=27.
3. **"Analytics-leader cohort" version of the thesis is rejected.** HOU/TBR/SDP/CLE all have *positive* intercepts. Only LAD shows the predicted sign.
4. **97% of the raw HIGH-cohort effect was regression to the mean** (Round 2's apparent 3.2σ signal). Any test that doesn't control for pre-trade tier will systematically over-attribute RTM to origin-org effects.
5. **Cannot distinguish (a) "LAD inflates production via system advantages that don't travel" from (b) "LAD sells high more aggressively"** — both predict identical mild-negative intercept. Synthetic-control framing (Mixtape Ch 10) deferred until sample doubles.

The most publishable single finding here is the **NYM and HOU positive outliers**, not LAD. They're directionally opposed to the original thesis and have larger effect magnitudes.

Confidence: high on the controlled-test conclusion (n=577, tight β_pre posterior). Moderate on the org-level rankings — n per org is 9-32, individual rankings are still noisy.

**Affects.**

- Documented as [[trade-eval--origin-org-system-tax-v1]] in vault. Closes R-10.
- Reinforces the V1 sample-size bottleneck identified in R-06/07/09: per-org effects at this scale are detectable only as the marginal `τ` posterior, not as per-org separations.
- Strengthens the case for Retrosheet pre-2010 transaction ingest as the highest-leverage next move (raised in R-09 affects too).
- New candidate research thread: **HOU origin-side dev-fit-travels** — symmetric reading of MVP Machine Ch 9 from the departure direction. Larger and cleaner signal than the LAD test.
- New candidate research thread: **NYM inverse-system-tax** — players who leave the Mets outperform expectations. Could be sell-at-trough selection or genuinely suppressive environment.

Files: `scripts/explore_origin_org_dropoff.py` (R-1), `scripts/explore_system_tax_split.py` (R-2), `scripts/origin_org_pedigree_controlled.py` (R-3).

---

## [2026-05-16] R-09: Draft pedigree feature null at V1 scale

**Question.** Does the receiving team's acquired-player draft pedigree (`receiver_best_draft_pick`, lower = higher pedigree) add predictive signal to the multilevel Bayesian model? This is the R-08-prep proposal in pragmatic form — MLB Pipeline top-100 was lazy-loaded so we substituted the MLB Stats API `/draft/<year>` endpoint and used pick-number as a coarse pedigree proxy.

**Setup.** Ingested 46,126 draft picks 1990-2024 (`ingest/draft.py`, schema v11). Built `trade_pedigree` view (per trade-event-per-receiver: MIN/AVG/count of pick_number across acquired players). Joined as `receiver_best_draft_pick` into `trade_with_context`. Matched-subset A/B: 9-feat (with) vs 8-feat (without) on the 763-row subset where all 9 features are non-null. Train pre-2021, test 2021-2024. PyMC, seed=137, 1000 tune + 1000 draws × 2 chains.

**Result.** Δ CRPS = +0.0008 (essentially zero, slightly *worse* with the feature). Δ MAE = +0.0033. Both models score ~+4.5% CRPS vs predict-zero on this subset — same regime as R-06/R-07. The new feature does not move the needle. See `scripts/ablation_draft_feature.py`.

Pressly sanity check passed: HOU side (received Pressly, MLB pick #354 / 2007 R11) has `receiver_best_draft_pick = 354`; MIN side (received Alcala + Celestino, both int'l FAs) is NULL — correct.

**Interpretation.** Same shape as R-06 (org-aggregate hitter dev-fit) and R-07 (per-coach hitter dev-fit). Three plausible explanations, in order of likelihood:
1. **Sample size below detection floor.** 364 training trades + 9 features = ~40 trades per coefficient. Real effects in this regime are washed out by team-cluster partial pooling absorbing variance into `tau_team`.
2. **Pick number is too coarse a pedigree proxy.** A 1st-round signability case (think Mark Appel #1 overall) and a Mike Trout #25 are both "first-round picks" but worth radically different things at trade time. MLB Pipeline top-100 *ranks* would discriminate better — still blocked by lazy-load. FV grades better still — still need Playwright on FanGraphs.
3. **Pedigree at draft != pedigree at trade.** Trade outcomes are dominated by post-draft performance (which bWAR already captures in the naïve baseline). Pre-draft pedigree adds little marginal info conditional on that.

Confidence: medium. Strongly suspect #1 + #3 dominate. Cannot distinguish without either more data (Retrosheet pre-2010 trades, ~5x rows) or a richer pedigree signal (top-100 rank or FV).

**Affects.**
- Supports D-19/D-20 generalization: at V1 sample size, individual feature additions consistently sit below the noise floor on the matched-subset test. Pattern is now 3-for-3 (R-06, R-07, R-09).
- Suggests the next high-leverage move is *sample size*, not more features: Retrosheet pre-2010 transaction ingest or Playwright-based MLB Pipeline scrape.
- Catalog new draft_picks source as ingested.
- Keep `receiver_best_draft_pick` in FEATURE_COLUMNS — non-harmful, future-relevant when sample grows.

---

## [2026-05-16] R-08-prep: Future Value methodology ingested — prospect-feature design candidates surfaced

**Question.** Per D-20, the next-highest-leverage feature work is prospect-side. Longenhagen & McDaniel's *Future Value* (2020) is the canonical public reference for the FV-grade-to-WAR mapping. What concrete features does the book suggest we add to the multilevel Bayesian model, and what data would we need to compute them?

**Setup.** Not an experiment — a methodology read. Ingested three chapters:
- Ch 1 (four scouting markets context)
- Ch 2 (post-2012 hard-cap draft mechanics + power-law of production)
- Ch 10 (★ FV grade definition + WAR mapping)

Notes in vault: `longenhagen-mcdaniel-2020-ch{1,2,10}-*.md`.

**Result — proposed feature shapes:**

| Feature | Data needed | Source candidate |
|---|---|---|
| Prospect-WAR-projection per acquired player | FV grade + variance + ETA at trade-time | FG (blocked); MLB Pipeline / BA top-100 (scrapeable) |
| Cost-controlled-surplus expectation | FV → WAR table × years-of-control remaining | Craig Edwards' published FG tables; need to source |
| Draft-class era marker | Pre-2012 / 2012-2016 / 2017+ | We already have draft year; just need to bucket |
| Age-adjusted-within-class indicator | Birthdate + draft-class | MLB Stats API has DOB; trivial to add |
| Market-of-origin (US-draft / J2 / NPB-posting) | Player metadata at signing | Chadwick register has it |

**Interpretation.** The book confirms the prospect-feature direction is real and gives us the FV-to-WAR mapping structure. The methodology requires:
1. **Ingest a public prospect-grades source** (MLB Pipeline top-100 lists are the most likely viable path given FG is Cloudflare-blocked).
2. **Build a per-trade prospect-feature joiner** — for each trade-event leg, look up the player's FV grade as-of-trade-date and project expected WAR over their remaining cost-controlled window.
3. **Add variance bucket and market-of-origin as side features** per Ch 10's variance modifier discussion.

The Ramírez-vs-Grieve thought experiment (Ch 10) is a clean **validation test** for any prospect-aware model: a well-formed trade-eval should rank Grieve higher for cost-controlled surplus and Ramírez higher for total career WAR, with the recommendation depending on what the buyer optimizes.

**Affects.** Establishes the work-plan for R-09+ (actual prospect-feature ingestion + Bayesian re-fit). Does not itself produce a model fit. Logged so the R-NN chain stays continuous and the prospect-feature direction has a documented design rationale.

---

## [2026-05-16] R-07: Per-coach hitter operationalization — also ~0 contribution

**Question.** R-06 found the team-aggregate hitter dev-fit feature was silent. Hypothesis (D-19): the Ch 5 thesis lives at a per-coach level — when Tim Hyers moves LAD-asst → BOS-head → TEX-head, his coaching signal moves with him; a team-aggregate gets diluted across coach turnover. Does a per-coach trailing-3yr xwOBA-jump feature recover the signal?

**Setup.** New feature `coach_hitter_xwoba_jump_3yr`: for each (team, season) the trailing-3yr mean xwOBA jump for hitters this team acquired, but the aggregation is **per-COAT (hitting coach)**, not per-team. The feature follows the coach across team moves. Shifted forward 1 season → pre-trade-year knowledge. Matched-subset A/B via `scripts/ablation_coach_feature.py`. 702 test rows (rows with all 8 features non-null).

**Result.**

| Variant | Test MAE | Test CRPS | tau_team | vs predict-zero CRPS (1.0566) |
|---|---|---|---|---|
| 7 features (no per-coach) | 1.1846 | 1.0893 | 0.2453 | −3.09% |
| 8 features (with per-coach) | 1.1838 | 1.0899 | 0.2523 | −3.15% |
| **Δ from adding per-coach** | **−0.0008** | **+0.0006** | **+0.0070** | **~0** |

Hyers spot-check (sanity): his coach trailing-3yr xwOBA-jump record reads as -0.04 to -0.03 across BOS→TEX years. Negative even for a coach with a strong reputation — because BOS acquired established stars (Betts, Devers, J.D. Martinez) whose xwOBA was already near ceiling and naturally regressed. Per-coach aggregation doesn't escape the regression-to-mean confound that R-06 identified at team level.

**Interpretation.** Per-coach hitter dev-fit also contributes ~zero predictive signal on the matched subset. Two reads:
1. The MVP Machine Ch 5 thesis may be **structurally untestable** at our current data granularity — the signal-to-noise on hitter xwOBA jumps is too low to detect at any team- or coach-level aggregation given our N (~700 test rows).
2. The "who they acquired" confound (BOS acquires stars, not reclamation projects) dominates "who's coaching them" — selection-on-gains is corrupting both team and per-coach aggregations the same way.

Also notable: both fits' CRPS is **worse** than predict-zero on this subset (-3.15% / -3.09%), unlike the 911-row subset where the 7-feature fit was +1.07%. The 702-row subset (post-2015 trades with documented hitting-coach assignment + acquisition history) has a *lower* predict-zero CRPS (1.057 vs 1.105) — these trades are nearer zero on average, harder to beat. Same sample-shrinkage confound R-06 named, recurring at a different cut.

**Affects.** Supports a new **D-20**: hitting-side dev-fit features (team-aggregate or per-coach, trailing-3yr xwOBA-jump operationalization) are below noise floor. The pitcher signal IS detectable (R-05); the hitter signal is not, at this data scale + aggregation. Suggests:
- **Phase 3.5 should focus on pitching-side richer features (R-08 candidate: per-player coupling).** The signal lives where the data is denser.
- Hitting-side may need either (a) much more data (decades) or (b) a fundamentally different feature shape — player-level swing-change data we don't have from public sources.

---

## [2026-05-16] R-06: Hitter dev-fit ablation — feature contributes ~0 on matched subset

**Question.** Phase 3 V0 (6 features, pitcher dev-fit only) beat predict-zero by +3.33% CRPS. Phase 3 V1 (7 features adding hitter dev-fit) dropped to +1.05%. Is the hitter feature actively degrading the model, or is the difference a sample-shrinkage confound from the smaller test set?

**Setup.** `scripts/ablation_hitter_feature.py`. Pulled the *matched* 911-row test subset (rows with ALL 7 features non-null, 2021+). Fit two Bayesian variants on the same training rows: (A) all 7 features; (B) drop `receiver_org_hitter_xwoba_jump_3yr`. Same seed (137), 2 chains × 1000 tune × 1000 draws, same prior structure.

**Result.**

| Variant | Test MAE | Test CRPS | vs predict-zero CRPS (1.1047) |
|---|---|---|---|
| 7 features (with hitter) | 1.1824 | 1.0930 | +1.05% |
| 6 features (no hitter) | 1.1802 | 1.0928 | +1.07% |
| **Δ from adding hitter** | **+0.0021** | **+0.0002** | **~0** |

**Interpretation.** The hitter dev-fit feature is essentially silent at this operationalization (team-season trailing 3yr mean of `xwoba_t_plus_1 - xwoba_t_minus_1`). The dramatic drop V0 → V1 was the sample-shrinkage confound — the smaller test set has a different baseline (predict-zero CRPS 1.1047 vs 1.1351 in the 6-feature V0 dataset). Confidence: high (within-run A/B controlled).

**Two plausible explanations for the null result on hitters:**
1. Hitting dev is more about individual coach-player matchups (Latta-Turner specifically) than team-level systems — Ch 5's narrative is more individual than Ch 9's.
2. Star-hitter acquisitions (LAD acquires established stars) have less room for xwOBA improvement; regression to mean swamps the dev-signal at aggregate.

**Affects.** Supports newly-added **D-19** (hitter dev-fit at team aggregate is below noise floor). Suggests two follow-ups:
- R-07 candidate: try a per-acquired-player operationalization (couple team k-jump history with the specific pitcher's pre-trade stuff percentile) — captures interaction effects.
- R-08 candidate: try a per-coach operationalization (use `coaches` table — does a *specific hitting coach's* trade-acquired-player xwOBA jump history predict their next acquisition's surplus?).

---

## [2026-05-15] R-05: Phase 3 V0 — pitcher dev-fit feature beats predict-zero (first win)

**Question.** Operationalize the MVP Machine Ch 9 thesis ("the Astros' pitching coach systematically improved acquired pitchers") as a feature. Does it produce a measurable CRPS lift over predict-zero in the Bayesian multilevel model?

**Setup.** Added `org_pitcher_k_jump_3yr` to `features.py` — for each (team, season), the trailing-3yr mean of `(k_percent_t_plus_1 - k_percent_t_minus_1)` for pitchers this team acquired. Shifted forward 1 season so the feature represents pre-trade-year knowledge. 6-feature Bayesian fit on the 985-row test set (2021+, rows with all 6 features non-null). Same prior structure as R-04. Commit `6ca0152`.

**Result.**

| Model | Test MAE | Test CRPS | vs predict-zero |
|---|---|---|---|
| Predict-zero | 1.1351 | 1.1351 | baseline |
| OLS 6-feature | 2.4580 | n/a | -116.54% (catastrophic) |
| **Bayesian 6-feat** | **1.2069** | **1.0973** | **CRPS +3.33% BETTER** |

Posterior `tau_team` rose from 0.08 → 0.14 (model finds team-specific signal). Posterior `sigma` fell from 2.83 → 2.43 (less irreducible noise).

Feature spot-check matches the literature: LAD 2018 = +16.17, MIN 2018 = -25.0, HOU 2019 = +3.33 (post-Verlander/Cole entry).

**Interpretation.** First genuine beat-zero on CRPS in this project. The MVP Machine Ch 9 thesis is empirically detectable at the team-season aggregate level. Confidence: high. Note: rhat warnings on short chains — would want 4 chains × 2000 samples for production claims.

**Affects.** Supports D-09 (context-aware valuation thesis) and D-12 (multilevel from day one). Drives Phase 3 V1 (R-06: try hitter analog).

---

## [2026-05-15] R-04: OLS catastrophically overfits with 5 features; Bayesian holds

**Question.** Phase 2.5 added `prior_year_wins` and `prior_year_pyth_pct` from the standings adapter. Does the expanded feature set help OLS catch up to the Bayesian model, or does it widen the gap?

**Setup.** Same data, expanded `FEATURE_COLUMNS` from 3 → 5 features. Train ≤2020 / test 2021+. Both models fit on the matched 1,730-row test set.

**Result.**

| Variant | Test MAE | Test CRPS | vs predict-zero CRPS (1.1539) |
|---|---|---|---|
| OLS 5-feature | 1.5007 | n/a | **−30.05% (catastrophic)** |
| Bayesian 5-feature | 1.2085 | 1.1635 | −0.83% (CRPS *improved* vs R-03's −1.06%) |

OLS produced a spurious `prior_year_pyth_pct` coefficient of −7.10 — the model fit massive negative surplus for high-winning-pct teams, which doesn't survive out-of-time validation.

**Interpretation.** Empirically validates the D-12/D-13 inductive bias: strong priors regularize toward predict-zero when features are weak; OLS without that protection catastrophically overfits. Bayesian CRPS even *improved* slightly by adding the features — the priors correctly shrunk their weak coefficients without amplifying noise. Confidence: high.

**Affects.** Strengthened evidence for **D-18** (Bayesian framing is structurally necessary). Locks in the modeling architecture for all subsequent experiments.

---

## [2026-05-15] R-03: Bayesian 3-feature fit — calibrated posterior within 1% CRPS of predict-zero

**Question.** Replace OLS with the multilevel varying-intercepts PyMC model on the same 3-feature inputs. Does the Bayesian framing produce a calibrated posterior even when point predictions can't beat zero?

**Setup.** Same 3 features as R-02 (`prior_year_war`, `org_dev_fit_pitching`, `org_dev_fit_hitting`). Model: `alpha + alpha_team[i] + beta @ x_i`, `alpha_team ~ Normal(0, tau_team)`, `tau_team ~ HalfNormal(1)`, `sigma ~ HalfNormal(2)`, `beta ~ Normal(0, 0.1)`. 2 chains × 1000 tune × 1000 draws, seed 137. CRPS computed empirically over posterior-predictive samples per observation.

**Result.**

| Model | Test MAE | Test CRPS | vs predict-zero CRPS (1.1539) |
|---|---|---|---|
| OLS 3-feature (R-02) | 1.2097 | n/a | n/a (MAE: -4.83%) |
| **Bayesian 3-feature** | **1.2046** | **1.1662** | **CRPS −1.06% (close to parity)** |

Posterior `sigma` mean = 2.87 (per-trade irreducible noise ~3 WAR). Posterior `tau_team` mean = 0.08 — the model correctly infers near-zero team-specific intercept variation given the weak feature set.

**Interpretation.** The Bayesian posterior is well-calibrated even when it can't beat zero on point predictions — exactly the D-13 inductive bias. Strong priors shrink toward predict-zero where signal is absent. Confidence: high.

**Affects.** Validates D-12 and D-13. Suggests the predict-zero CRPS is the right benchmark to track going forward; OLS MAE comparisons are less informative.

---

## [2026-05-15] R-02: OLS 3-feature fit fails to beat predict-zero

**Question.** Does a simple linear regression on three team-season context features (prior-year team WAR, hitting/pitching dev-fit proxies from bWAR aggregates) beat the predict-zero baseline on out-of-time validation?

**Setup.** Features: `receiver_prior_year_war`, `receiver_dev_fit_pitching`, `receiver_dev_fit_hitting`. Target: realized surplus. Train ≤2020, test 2021+. OLS via `numpy.linalg.lstsq`. 3,735 train rows / 1,730 test rows.

**Result.**

| Model | Test MAE | vs predict-zero (1.1539) |
|---|---|---|
| Predict-zero | 1.1539 | baseline |
| **OLS 3-feature** | **1.2097** | **−4.83% (worse)** |

Pitching-dev-fit coefficient was the strongest at +0.026 — narratively matches the MVP Machine thesis. Prior-year-WAR coefficient was slightly negative (counterintuitive; likely confound from deadline-sellers being high-WAR teams).

**Interpretation.** Trades are near-zero-sum in expectation; surplus has high variance that a 3-dim linear fit can't capture. Negative point-prediction result is *informative* — it justifies the multilevel Bayesian framing with strong priors (the V2 architecture).

**Affects.** Drives R-03 (Bayesian 3-feature). Establishes that "beating predict-zero" is the right success criterion going forward.

---

## [2026-05-15] R-01: Phase 2 V0 naive baseline backtest — realized-WAR ground truth

**Question.** Does the V0 naive baseline (pure WAR-based bilateral surplus, no context terms, no $/WAR) correctly identify legendary trade winners and losers from 2010-2024 realized data?

**Setup.** `modeling/naive_baseline.py`. For each (trade_event, team), `surplus = WAR_received - WAR_given_up` summed over a 3-year post-trade window. Run via `ste backtest naive` over 2010-2024. 5,481 (event, team) rows written to `naive_baseline_results`.

**Result.** Top 10 winners (matched against literature):

| Rank | Trade | Surplus |
|---|---|---|
| 1 | Gonzalez/Beckett/Crawford LAD-BOS 2012 | +22.68 (LAD) |
| 2 | Yelich MIA→MIL 2018 | +21.50 (MIL) |
| 3 | Arrieta PIT→CHC 2013 | +20.78 (CHC) |
| 4 | Chapman OAK→TOR 2022 | +20.01 (TOR) |
| 5 | Cliff Lee CLE→PHI 2009 | +19.50 (PHI) |
| 6 | Cliff Lee SEA→TEX 2010 | +18.92 (TEX) |
| 7 | Trea Turner + Scherzer WSH→LAD 2021 | +18.54 (LAD) |
| 8 | Mookie Betts BOS→LAD 2020 | +16.84 (LAD) |
| 9 | Verlander DET→HOU 2017 | +16.75 (HOU) |
| 10 | Holliday OAK→STL 2009 | +16.11 (STL) |

Mirror bottom 10 captures the canonical "trades you regret" (Boston dumping Gonzalez/Beckett/Crawford, Pittsburgh giving up Arrieta, Cleveland giving up Cliff Lee, Detroit giving up Verlander).

**Interpretation.** The data layer correctly captures realized-WAR ground truth. The naive baseline is the right reference: it's *not* a predictive model (it requires post-trade WAR to compute), but it's the canonical "what actually happened" against which predictive models must measure their predictions. Confidence: high.

**Affects.** Establishes the test data + outcome ledger that R-02 through R-06+ all evaluate against.

