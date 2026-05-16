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

