# Evaluation

What has to happen before a number in this repo is allowed to be stated as fact.

The short version: diagnose with distributions, not single trades. A canonical
case study is a poor anchor, because shrinkage pulls tail outcomes toward the
regime mean by design and fitting one outlier tightly is overfitting. The real
diagnostics are held-out calibration, CRPS, and credible-feature counts.

## The benchmark

`scripts/benchmark_vs_naive.py` is the GO gate. It scores the production model,
the structural two-part model in `modeling/structural.py`, against the baselines
on a holdout it never trained on, and exits nonzero on failure. V3 is scored in
the same run for comparison.

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
| V3 (posterior mean) | 1.143 | 1.026 | 83.5% | 38.1% |
| **Structural two-part (production)** | **1.079** | **0.867** | 91.5% | |

Verdict: **GO** for the structural model: 4.3% better than the median null on
MAE, 11.1% better than climatology on CRPS, and 91.5% coverage of the 90%
interval. V3 on the same rows is 1.4% worse than the median null and 5.3% worse
than climatology. Changing the target fixed what is being measured; it did not
give V3 skill.

The same script on the old target, for the record:

| Model, target `war_delta` | MAE | CRPS | Cov90 | P(direction) |
|---|---|---|---|---|
| Null (train mean) | 1.242 | | | 37.2% |
| **Null (train median = 0)** | **0.894** | | | 42.8% |
| **Climatology (train distribution)** | | **0.773** | | |
| Marcel linear | 1.400 | | | 37.0% |
| V3 (posterior mean) | 0.914 | 0.827 | 81.3% | 31.9% |

V3 is NO-GO there too: 2.3% worse than the median null on MAE and about 7%
worse than climatology on CRPS. The gate on either target is beating the median
null and Marcel on MAE, climatology on CRPS, and holding 90% coverage at or
above 80%. MAE moves by about 0.001 between runs.

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
| B. T-1 WAR, two-part | 1.241 | 0.984 | 91.7% |
| **C. Structural, two-part** | **1.207** | **0.961** | 90.3% |
| D. The 34 context features, two-part | 1.342 | 1.096 | 90.1% |
| E. Structural + 34 context, two-part | 1.237 | 0.963 | 90.5% |

C had the best fold CRPS and was scored on the 2018-2021 holdout (n=1100):

| Model | MAE | CRPS | Cov90 |
|---|---|---|---|
| Null (median / climatology) | 1.127 | 0.975 | |
| V3, 34 features, Student-t | 1.143 | 1.026 | 83.5% |
| **C. Structural, two-part** | **1.079** | **0.867** | 91.5% |

Four features beat both nulls out-of-sample, by 4.3% on MAE and 11.1% on CRPS,
with intervals that cover at the stated rate. This is the first model in the
repo to do so.

One change was made after the first holdout score. The zero/non-zero classifier
was tuning its regularization on accuracy, which a unit test on separable data
showed gives poorly calibrated probabilities. It now tunes on log-loss. On the
folds, spec C is unchanged to three decimals and B and E improve. On the
holdout, C moved from 1.065 / 0.865 to 1.079 / 0.867. The decision was made on
the folds and the holdout number is reported as it fell.

The 34 context features carry no detectable signal in this model class. Alone
(D) they are worse than the median null on MAE; added to the structural
features (E) they do not improve on C (fold CRPS 0.963 against 0.961). Only 11 of
the 34 have usable coverage; the acquired-player ones are almost entirely
mean-imputed (FanGraphs FV 1%, Statcast 6%).

### Club context on top of the structural model (R-65)

`scripts/r65_context_on_structural.py` tests context in the form where it should
matter, as a multiplier on how much of a player's talent the club captures
(playing time) or keeps after control ends (retention). The specs, the five
team-level columns and the decision rule were fixed before any spec was scored:
a spec earns one look at the holdout only if its paired per-side CRPS gain over
the structural model has a 99% interval above zero (five comparisons) and it
wins at least 3 of 4 folds. The five columns are the contention-window score,
prior-year pythagorean percentage, payroll as a share of the cap, and hitting
and pitching development fit. Pre-2018 walk-forward folds, n=1169 sides:

| Spec | CRPS | Gain vs structural | 99% half-width | Folds better |
|---|---|---|---|---|
| S0. Structural | 0.9607 | | | |
| S1. + context, additive | 0.9646 | -0.0040 | 0.0051 | 0 of 4 |
| S2. + context x held WAR | 0.9631 | -0.0025 | 0.0125 | 1 of 4 |
| S3. + context x post-control held WAR | 0.9602 | +0.0005 | 0.0109 | 2 of 4 |
| S4. + contention x held WAR | 0.9591 | +0.0016 | 0.0088 | 3 of 4 |
| S5. + payroll x post-control held WAR | 0.9605 | +0.0002 | 0.0066 | 3 of 4 |

No spec earned a holdout look, so the holdout was not touched. Club context, in
these five columns and these two multiplicative forms, adds nothing detectable.

What that does and does not rule out. Planting a known effect in the same
pipeline, a context column that moves captured WAR by 10% of held WAR per
standard deviation (about 0.26 WAR per side) is detected (CRPS gain 0.023
against a 0.021 half-width); 5% is not. So an effect of that size or larger in
one of these columns would have shown up. Smaller effects cannot be excluded at
this sample size. Not tested: positional need and roster displacement (who the
acquired player would actually replace), tested next in R-66 below, and
team-level random effects, which R-33 to R-35 already found add nothing.

### Roster displacement (R-66)

`scripts/r66_displacement.py` tests the mechanism the contention columns could
not: a player is worth less to a club that already has someone good at his
position. For each acquired player the script takes the receiving club's
incumbent strength, the mean WAR of the top-k players in his position group the
season before he arrives (C, 1B, 2B, 3B and SS one slot each, OF three, SP five,
RP six; pitchers are SP if they started at least half their games), excluding
him. Three specs were fixed before scoring, with the same rule as R-65: a 99%
paired CRPS interval above zero and at least 3 of 4 folds to earn one holdout
look. Pre-2018 folds, n=1169 sides, 44% of which have the feature (position
known and MLB history):

| Spec | CRPS | Gain vs structural | 99% half-width | Folds better |
|---|---|---|---|---|
| S0. Structural | 0.9607 | | | |
| P1. + mean incumbent strength | 0.9584 | +0.0022 | 0.0058 | 3 of 4 |
| P2. + incumbent strength x held WAR | 0.9585 | +0.0022 | 0.0057 | 3 of 4 |
| P3. + displaced WAR | 0.9503 | +0.0104 | 0.0175 | 3 of 4 |

No spec earned a holdout look, so the holdout was not touched. P3, displaced WAR
(held WAR times the incumbent's share of the player's own rate, capped at one),
is the largest gain any context test has produced, about 1.1% of CRPS, but its
interval runs from roughly -0.007 to +0.028.

The direction matches the mechanism, which was not part of the decision rule.
With held WAR fixed, the ridge coefficient on displaced WAR is negative (-0.93
standardized), and the median of captured WAR over held WAR falls from 0.26 to
0.05 as the displaced share rises from none to over 60%. The classifier
coefficient is positive (+0.97) because displaced WAR is zero for players with no
MLB track record, so it partly encodes having one. The mean ratio is flat
(0.36, 0.38, 0.40, 0.30) because a few large seasons dominate it, and the
lowest-share buckets have 29 and 49 sides.

Read as: displacement is plausibly real and not yet demonstrable at 1,169 test
sides. Spending the holdout on P3 now would not meet the rule set in advance.
Limits: incumbents come from the previous season's bWAR, not the roster on the
trade date; position is career primary position; depth beyond the top slots,
injuries and platoons are ignored.

The decision-level score does not separate any of these. Per-trade gain has a
95% half-width of about 0.45 to 0.50 WAR at n of 300 to 360 trades:

| Picker | Folds: won, WAR per trade | Holdout: won, WAR per trade |
|---|---|---|
| C. Structural, two-part | 48.6%, +0.31 | 54.3%, -0.05 |
| More T-1 WAR | 55.4%, +0.05 | 55.5%, +0.51 |
| More held WAR (unfitted) | 50.4%, -0.17 | 61.7%, +0.64 |

Every picker looks good in one period and flat in the other. Trades that happen
are ones both clubs judged close to fair, so "who won" on completed trades is
near a coin flip by construction and has a low ceiling as a test. It stays in
the benchmark as a diagnostic. The proper scores above are the gate.

Known limits: service time is counted in MLB seasons played, not days, and no
historical contract data is used, so a veteran on a multi-year deal looks like a
rental. The 2020 season was 60 games and sits inside every holdout window.

## In production

`ste score-trade` reports `Captured WAR` from `structural.score_players` as the
headline row, with `--date` setting how much of the season is left. The
production fit trains on trades from 2010 through 2020, the last season whose
T+5 window is complete in bWAR. If the latest bWAR season is still in progress,
a trade dated after it is priced as an in-season trade as of the data, and the
output says so.

The V3 rows (`WAR Delta`, `Dollar Surplus`, `Surplus Wins`) are still printed and
are labelled as not validated.

The War Room trade workshop shows the same forecast. `scripts/export_structural.py`
writes the model parameters and each rostered player's features to
`frontend/src/data/model/structural_model.json`, and the card evaluates the
package in the browser (`frontend/src/lib/structural.ts`). Both sides use one
analytic summary: the residual pool is compressed to 200 quantile atoms, so the
mean, interval and P(receive side ahead) need no random draws and are identical in
Python and TypeScript. `npm run check:structural` runs the TypeScript against 55
Python-computed golden cases (max absolute error 5e-13) and fails if they
diverge; corrupting one parameter makes it fail. The holdout facts printed under
the card (coverage, CRPS gain, favoured-side win rate) are written by the
benchmark to `structural_validation.json`, so the card shows the benchmark's
numbers. The card's headline is gross WAR with salary beside it: the dev-system
multiplier, deadline premium, dollar conversion and recommendation labels are gone
because none was validated.

The standalone Trade Builder shows the same forecast and the same footnote, through
shared code (`comparePackages`, `leanOf`, `ForecastFootnote`), so one trade gives
one answer on both screens. Its banner says "leans toward what you receive", "close
to even" or "leans toward what you send" instead of accept or reject, because the
higher-forecast side won only 54% ± 6 of past two-sided trades. The distribution
plot is drawn from the model's own atoms, so the exact-zero case and the skew are
visible. The AI reasoning prompt carries the forecast, its interval and the
validation facts, and tells the model what the forecast cannot see (club context,
roster displacement, prospects, injuries, salary) instead of citing ADR principles
that the evidence no longer supports. The browser-side `computeVerdict`, its
heuristic helpers and the pseudo-posterior violin were deleted.

Still on the old browser-side heuristic: the buy-low and deals-that-clear engines
and the package skeletons that feed the AI brief. `suggest-trades` and trade
cycles still rank on V3 `war_delta`. The
structural model has no club-context term, so it cannot rank the same player
differently for different clubs; those tools depend on exactly that, and they are
unvalidated until a context effect beats the structural model on the folds.
Prospects are not in the validated forecast (the model has no prospect term);
the card shows their FV-table value on a separate line, marked unvalidated.

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
