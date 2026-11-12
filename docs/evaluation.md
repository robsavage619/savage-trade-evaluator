# Evaluation

What has to happen before a number in this repo is allowed to be stated as fact.

The short version: diagnose with distributions, not single trades. A canonical
case study is a poor anchor, because shrinkage pulls tail outcomes toward the
regime mean by design and fitting one outlier tightly is overfitting. The real
diagnostics are held-out calibration, CRPS, and credible-feature counts.

## The benchmark

`scripts/benchmark_vs_naive.py` is the GO gate. It scores V3 against two
baselines on a holdout the model never trained on and exits nonzero on failure.

- **Holdout:** 2018-2021 trade seasons, n=1100.
- **Train:** pre-2018, n=1874, for every model. V3 is refit inside the script;
  the cached production fit trains through 2022 and has seen the holdout.
- **Outcome:** `captured_war`, the WAR acquired players earned for the receiving
  club from T through T+5, summed per trade side. It replaced `war_delta` as the
  graded target on 2026-11-12; the reason is in "What the target measures"
  below. `benchmark_vs_naive.py war_delta` still grades the old one.

| Model, target `captured_war` | MAE | CRPS | Cov90 | P(direction) |
|---|---|---|---|---|
| Null (train mean) | 1.619 | | | 40.4% |
| **Null (train median = 0)** | **1.127** | | | 33.2% |
| **Climatology (train distribution)** | | **0.975** | | |
| Marcel linear | 1.851 | | | 40.5% |
| V3 (posterior mean) | 1.143 | 1.027 | 83.3% | 37.4% |

Verdict: **NO-GO**. V3 is 1.4% worse than the median null on MAE and 5.3% worse
than climatology on CRPS. Changing the target fixed what is being measured. It
did not give the model skill.

The same script on the old target, for the record:

| Model, target `war_delta` | MAE | CRPS | Cov90 | P(direction) |
|---|---|---|---|---|
| Null (train mean) | 1.242 | | | 37.2% |
| **Null (train median = 0)** | **0.894** | | | 42.8% |
| **Climatology (train distribution)** | | **0.773** | | |
| Marcel linear | 1.400 | | | 37.0% |
| V3 (posterior mean) | 0.914 | 0.827 | 81.3% | 31.9% |

Also NO-GO: 2.3% worse than the median null on MAE and about 7% worse than
climatology on CRPS. The gate on either target is beating every baseline and
holding 90% coverage at or above 80%. MAE moves by about 0.001 between runs.

CRPS is computed with `metrics.crps_empirical`, which is tested against the
closed form. The script's earlier local CRPS function was wrong (0.82 where the
tested one gives 0.55 on standard-normal draws) and has been deleted.

This replaces an earlier GO (2026-11-12 correction). That run had two faults.
It scored the cached production fit, trained through 2022, on the 2018-2021
holdout, so V3 was in-sample. And its only constant baseline was the train
mean, while 42.8% of holdout legs have `war_delta` exactly 0, which makes the
median the MAE-optimal constant. The reported 28.2% beat came from those two
together.

What the table says now: the outcome is zero-inflated, and a single Student-t
regression does not separate "this leg never produced MLB value" from "how much
value it produced". That is the modeling gap to close before any feature work.

## Decision level

MAE grades a number. A front office is graded on the decision, so the benchmark
also asks: across the 330 holdout trades with two receiving sides, did the side
the model favoured come out ahead?

| Picker | Truth | Favoured side won | WAR gained per trade | n |
|---|---|---|---|---|
| V3 trained on `captured_war` | WAR earned for the receiving club, T to T+5 | 55.7% ± 5.5 | +0.02 | 314 |
| V3 trained on `war_delta` | same | 50.6% ± 5.5 | -0.06 | 314 |
| More prior-year WAR | same | 55.5% ± 5.7 | +0.51 | 292 |

A coin flip scores 50% and zero. Training on the right target moved V3 from a
coin flip to the level of the one-line heuristic on win rate (54.1% to 55.7%
across three same-seed fits), but it gains nothing per trade: it gets the small
trades right and the large ones wrong. The heuristic gains about half a win per
trade. Neither is yet clearly better than a coin on win rate alone. Trades with no predicted or no realized
winner are dropped, which is why n differs by row. WAR only; salary is not
netted out.

## What the target measures

`scripts/r63_zero_outcome_audit.py` buckets every 2018-2021 leg (n=1388):

| Bucket | Legs |
|---|---|
| Nonzero WAR in the T+2 to T+5 window | 773 |
| Never reached MLB | 327 |
| MLB career ended before the window opened | 273 |
| Debuted after the window | 10 |
| Played in the window, WAR sums to zero | 3 |
| Absent inside the window only | 2 |

The zeros are real, not join failures: no bWAR row lacks a player id, and only 3
of the 327 never-reached names match a bWAR name. The career-ended group carried
almost nothing in the excluded years either (mean -0.08 WAR across T and T+1).

The target itself is the problem. `war_delta` is not a delta. It is the acquired
players' total WAR in T+2 to T+5 for any club, averaged per leg.

| Years after trade | WAR, any club | WAR for the receiving club | Share |
|---|---|---|---|
| 0 | 402.2 | 176.5 | 44% |
| 1 | 372.5 | 264.2 | 71% |
| 2 | 283.2 | 174.7 | 62% |
| 3 | 291.9 | 163.3 | 56% |
| 4 | 275.2 | 138.4 | 50% |
| 5 | 197.6 | 75.2 | 38% |

Of the 1,048 WAR in the target window, 552 (53%) was earned for the club that
made the trade. The window also leaves out T and T+1, where 441 of the 992 WAR
the receiving clubs actually captured (44%) was earned. Year 5 is partly
censored: 2026 is an in-progress season in the database.

## Baseline-up (R-64)

`scripts/r64_baseline_up.py` rebuilds the model from the simplest thing that
could work. Per acquired player: a 3-2-1 weighted WAR rate over the last three
completed seasons, times the seasons the receiving club can expect to hold him
inside the window, split into seasons under team control and seasons after it.
Summed per side, plus the number of players and the number with no MLB time.
Each spec is a two-part model: the chance a side produces non-zero WAR, times a
ridge regression on the non-zero sides, with an empirical residual distribution.

Specs were compared on pre-2018 walk-forward folds only (test seasons 2014 to
2017, n=1169 sides):

| Spec | MAE | CRPS | Cov90 |
|---|---|---|---|
| Null (median / climatology) | 1.324 | 1.128 | |
| A. T-1 WAR, plain regression | 1.279 | 1.030 | 90.7% |
| B. T-1 WAR, two-part | 1.252 | 1.009 | 90.6% |
| **C. Structural, two-part** | **1.207** | **0.961** | 90.3% |
| D. The 34 context features, two-part | 1.342 | 1.095 | 90.0% |
| E. Structural + 34 context, two-part | 1.240 | 0.972 | 90.5% |

C had the best fold CRPS and was scored on the 2018-2021 holdout (n=1100):

| Model | MAE | CRPS | Cov90 |
|---|---|---|---|
| Null (median / climatology) | 1.127 | 0.975 | |
| V3, 34 features, Student-t | 1.143 | 1.027 | 83.3% |
| **C. Structural, two-part** | **1.065** | **0.865** | 91.6% |

Four features beat both nulls out-of-sample, by 5.5% on MAE and 11.3% on CRPS,
with intervals that cover at the stated rate. This is the first model in the
repo to do so.

The 34 context features carry no detectable signal in this model class. Alone
(D) they are worse than the median null on MAE; added to the structural
features (E) they make the fit slightly worse than C. That is a result about
additive linear effects. Interactions, such as contention window with a rental,
were not tested.

The decision-level score does not separate any of these. Per-trade gain has a
95% half-width of about 0.45 to 0.50 WAR at n of 300 to 360 trades:

| Picker | Folds: won, WAR per trade | Holdout: won, WAR per trade |
|---|---|---|
| C. Structural, two-part | 48.6%, +0.31 | 54.6%, +0.10 |
| More T-1 WAR | 55.4%, +0.05 | 55.5%, +0.51 |
| More held WAR (unfitted) | 50.4%, -0.17 | 61.7%, +0.64 |

Every picker looks good in one period and flat in the other. Trades that happen
are ones both clubs judged close to fair, so "who won" on completed trades is
near a coin flip by construction and has a low ceiling as a test. It stays in
the benchmark as a diagnostic. The proper scores above are the gate.

Known limits: service time is counted in MLB seasons played, not days, and no
historical contract data is used, so a veteran on a multi-year deal looks like a
rental. The 2020 season was 60 games and sits inside every holdout window.

## The credibility bar

A feature is reported as credibly real only when both hold:

1. Its 90% credible interval excludes zero.
2. At least 95% of posterior mass falls on one side.

Under walk-forward cross-validation the directional threshold rises to 97.5% and
a feature must clear it in at least K of N folds with a consistent sign. Anything
that passes the single-split bar but fails the walk-forward bar is labeled
**EXPLORATORY**, not credible. See
[EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md) for the fold table.

This bar exists because the ablation phase ran 56 feature variants against one
2021-2024 holdout. Every one of them saw the same test window before a decision
was recorded, which is a textbook multiple-comparisons setup. Findings from that
phase were re-derived under the stricter standard rather than grandfathered.

## Leakage controls

- **Training-only imputation.** Missing test features are filled from training
  means, never from test statistics.
- **Feature winsorization.** Test features are clipped to
  `[training_mean +/- 5 * training_std]`, which matters most for Statcast-era
  features whose nulls would otherwise impute to a value far outside the
  early-era distribution.
- **Time-ordered splits.** Train on earlier seasons, test on later ones. No
  random shuffling of a panel.

## Revalidation

Any change that touches the model runs the D-38 protocol and the result is
committed with its git SHA, whether it passes or fails.

- **Go:** all three primary outcomes hold `coverage_90 >= 0.80`.
- **Stop:** any outcome below 0.80. Do not retrain, do not tweak. Record and
  report.

Reports live in [`revalidation/`](revalidation/). The
[baseline](revalidation/2026-07-baseline.md) is a pass. The
[post-MI report](revalidation/2026-07-post-mi.md) is a NO-GO and is committed for
the same reason: predict-time multiple imputation moved sparse-row coverage onto
nominal (0.87 to 0.94 on `war_delta`) while degrading CRPS 14.5% and 16.8%,
because independent per-feature draws ignore the correlations between them. The
change was reverted and the API kept for a future conditional-imputation
experiment.

## Per-prediction honesty

Two things ride along with every scored scenario:

- **A coverage grade.** Pre-imputation NaNs are counted per outcome and the row
  is graded A through D on observed fraction. C and D raise an extrapolating
  warning in the CLI and a colored chip in the UI.
- **Feature attribution.** `attribute_score` decomposes a score into
  `contribution_i = beta_mean_i * x_z_i * y_std` and returns the top contributors
  with observed/imputed and credible flags.

Neither fixes the underlying uncertainty. Both make it visible.

## Code-level checks

| Check | Command | Current |
|---|---|---|
| Tests | `uv run pytest -q` | 154 passing, 2.0s |
| Format | `uv run ruff format --check .` | clean |
| Lint | `uv run ruff check .` | clean |
| Types | `uv run pyright` | basic mode |
| Data quality | `uv run ste check` | seeded baseline, exits nonzero on drift |
| Full model smoke | `uv run python scripts/v2_full_backtest.py` | calibration plus credible-feature counts across outcomes |

CI runs format, lint, typecheck, and tests on every push to `main`.

The frontend has no test suite. 14,290 lines of TypeScript are checked by `tsc`
and by inspection, which is a real gap rather than a deliberate choice.

## Data-layer checks

The Pressly trade (MIN to HOU, July 2018, `transaction_id=371509`) is a fixture
for the ingest path, not evidence for the model. It checks that arsenal
percentiles, bWAR stints, and both-sides personnel still line up:

| Metric | T-1 (2017) | T (2018) | T+1 (2019) |
|---|---|---|---|
| Fastball spin percentile | 97 | 98 | 98 |
| Curveball spin percentile | 100 | 99 | 100 |
| K% percentile | 65 | 95 | 94 |
| Whiff% percentile | 69 | 98 | 95 |

The canonical comparison is T-1 against T+1. The trade-season row is listed so a
smoke-test mismatch can be attributed to the right year.

Stuff essentially unchanged, results transformed. That is the MVP Machine Ch 9
reading, reconstructed from raw data rather than asserted. If these numbers
drift, the data layer regressed; the canonical values are ground truth and are
not to be "fixed" to match a failing run.
