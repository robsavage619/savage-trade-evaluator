# Experiment Protocol — savage-trade-evaluator

**Version:** 1.0  
**Adopted:** 2026-05-20  
**Supersedes:** informal ablation process (R-01 through R-56)

This document is the **pre-registration template and methodology contract** for all
feature-credibility experiments conducted in this project. No experiment result may be
recorded as "confirmed" unless it was run under this protocol.

---

## Motivation

The ablation phase (R-01 → R-56) tested 56 feature variants on a single 2021-2024
holdout. All 56 saw the same test window before a decision was recorded — a textbook
case of researcher degrees of freedom. The multiple-comparisons exposure is
uncontrolled; any feature that looked good on this specific 4-year window is
capitalizing on chance by construction.

Three concrete pathologies identified:

| Pathology | Manifestation |
|---|---|
| Test-set contamination | Every CRPS check guides the next experimental decision |
| No multiple-comparisons control | 56 comparisons, 0 FDR corrections |
| n too small | kpct_delta n_test=77; per-fold walk-forward will drop below 30 |

---

## Standard: Walk-Forward Cross-Validation

All feature-credibility claims must be validated through walk-forward CV
(`modeling/v3_cv.py`) rather than single-split backtests.

### Split design

| Parameter | Value | Rationale |
|---|---|---|
| Split type | Expanding window | Matches production setting; no future-data leakage |
| Test window | 2 seasons | Enough trades per fold; preserves multiple folds |
| Minimum training seasons | 5 | Enough history for stable hierarchical priors |
| Step size | `test_window` (non-overlapping) | Independent test observations across folds |

**Practical fold counts (2026-05-20 data)**:

| Outcome | N folds | Note |
|---|---|---|
| war_delta | 5 | Full 2009-2023 trade history; robust multi-fold validation |
| dollar_surplus | 5 | Same population as war_delta |
| xwoba_delta | 1 | Statcast era only (2015+); single-fold = temporal robustness check, not multi-fold confirmation |
| kpct_delta | 1 | Same as xwoba_delta; all kpct results remain exploratory by design |

For outcomes with only 1 sufficient fold, the confirmation bar reduces to credible-in-1/1-fold with consistent sign (trivially satisfied). This is better than the old standard (same 2021-2024 window used 56 times) but weaker than a true multi-fold result. All xwoba_delta and kpct_delta results should be annotated as **EXPLORATORY** regardless of walk-forward result until more Statcast history accumulates.

### Sample-size gates

| Outcome | Min n_test per fold | Note |
|---|---|---|
| war_delta | 100 | 2+ seasons of mid-season trades |
| xwoba_delta | 50 | Statcast era (2015+) limits history |
| kpct_delta | 30 | Small population; exploratory if any fold < 50 |
| dollar_surplus | 100 | Derived from war_delta; same population |

Folds below the gate are computed and reported but marked **INSUFFICIENT**. They
do **not** count toward confirmation.

### Single-fold credibility threshold

A feature is credible in a fold if **both** of:
1. 90% posterior CI excludes zero (`p05 > 0` or `p95 < 0`)
2. Directional mass ≥ **97.5%** (stricter than ablation-phase 95%)

### Confirmation threshold

A feature is **CONFIRMED** if **all three** of:
1. Credible in ≥ `K/N` sufficient folds (see table)
2. Sign (direction) is consistent across **every** credible fold
3. At least one sufficient fold exists

| Outcome | Min credible fraction K/N |
|---|---|
| war_delta | 3/4 (75%) |
| xwoba_delta | 2/3 (67%) |
| kpct_delta | 2/3 (67%) |
| dollar_surplus | 3/4 (75%) |

Features that fail confirmation are **EXPLORATORY** — they may inform future
pre-registered hypotheses but must not appear in production feature sets.

---

## Pre-Registration Template

Every experiment must have a record filed **before** the script is run.
Record in `wiki/trade-eval--decisions.md` as a new entry:

```
### D-NN: <Feature name> — <Outcome>

**Status:** PRE-REGISTERED  
**Filed:** YYYY-MM-DD  
**Script:** scripts/rNN_<name>.py  

**Hypothesis:**
- Feature: `<column_name>`
- Outcome: `<outcome>`
- Predicted direction: positive / negative
- Mechanistic rationale: [1-3 sentences explaining WHY this feature should move the outcome]

**Falsifiability criteria (pre-committed):**
- Confirmed if: credible in ≥ K/N sufficient folds with consistent sign (per EXPERIMENT_PROTOCOL.md)
- Exploratory if: credible in some folds but fails K/N or sign-consistency gate
- Null if: fails single-fold credibility in all sufficient folds

**Sample size expectation:**
- Estimated n_test per fold for this outcome: ~N
- Folds expected sufficient: N of M

**Confounds to consider:**
- [List any known confounds or collinear features]
```

After results:

```
**Result:** CONFIRMED / EXPLORATORY / NULL  
**Run date:** YYYY-MM-DD  
**Fold summary:** [paste walk-forward report header]  
**Action:** [what changes in feature sets / V3_OUTCOME_FEATURES]
```

---

## Decision to Include in Production

A feature graduates from CONFIRMED to the production feature set only after:

1. Walk-forward confirmation recorded in `decisions.md`
2. `V3_OUTCOME_FEATURES` updated in `v3.py`
3. `ALL_FEATURES` / bucket tuples in `v2/features.py` updated if applicable
4. A commit tagged `feat: confirm <feature> for <outcome> (D-NN)`

---

## Numerical Stability Requirements

The following safeguards are implemented in `modeling/v3.py` and must remain active:

1. **Training-only imputation** — missing features in the test set are filled with the
   training set mean, not the global mean. Prevents test-data leakage in imputation.

2. **Feature winsorization** — test features are clipped to `[training_mean ± 5·training_std]`
   before standardization. Prevents catastrophic linear extrapolation when the test period
   contains out-of-distribution feature values (e.g., a feature not present in the training
   era receives a zero/imputed value that is far from the training distribution).

These are not optional. Walk-forward folds with early training windows (2009-2013)
commonly produce test observations with extreme standardized feature values on
Statcast-era features (null → imputed to a value far from early-era distribution).

## What Does NOT Count as Evidence

| Practice | Why it fails |
|---|---|
| Single-split backtest on 2021-2024 holdout alone | Single window, already used for selection |
| CRPS improvement < 0.001 in isolation | No uncertainty bound; could be noise |
| Credible in 1/4 folds | Consistent with false-positive rate at 97.5% mass |
| Directional mass 95-97.4% | Below new single-fold bar |
| Sign flips between folds | Model can't decide which direction; exploratory only |
| kpct_delta credibility claimed as "confirmed" without exploratory caveat | n too small in any individual fold |

---

## Known Exploratory Findings (Pre-Protocol)

The following were claimed "credible" under the old single-split standard (R-01 → R-56)
and are **not confirmed** under this protocol until R-57 walk-forward validation completes:

**war_delta** (claimed credible, must re-validate):
- `receiver_acquired_player_quality`
- `receiver_acquired_player_avg_war_trajectory`
- `receiver_dev_fit_pitching`
- `receiver_dev_fit_hitting`
- `receiver_org_pitcher_k_jump_3yr`
- `receiver_org_hitter_xwoba_jump_3yr`
- `receiver_total_payroll`
- `receiver_tech_adoption_lead_years`
- `receiver_alumni_network_score`
- `receiver_acquired_milb_hit_quality`

**kpct_delta** (claimed credible, likely exploratory given n=77 test):
- `receiver_acquired_pitcher_k_trajectory`
- `receiver_alumni_network_score`
- `receiver_tech_adoption_lead_years`

**xwoba_delta** (claimed credible, must re-validate):
- `receiver_acquired_player_quality`
- `receiver_tech_adoption_lead_years`
- `receiver_platoon_woba_diff`
- `receiver_org_hitter_xwoba_jump_3yr`

Status changes to **CONFIRMED** or **EXPLORATORY** when R-57 completes.

---

## Review and Revision

This protocol may be revised only by filing a decision (D-NN) explaining what changed
and why. The bar for raising thresholds is low; the bar for lowering them is high.
