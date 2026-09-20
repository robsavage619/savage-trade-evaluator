# Evaluation

What has to happen before a number in this repo is allowed to be stated as fact.

The short version: diagnose with distributions, not single trades. A canonical
case study is a poor anchor, because shrinkage pulls tail outcomes toward the
regime mean by design and fitting one outlier tightly is overfitting. The real
diagnostics are held-out calibration, CRPS, and credible-feature counts.

## The benchmark

`scripts/benchmark_vs_naive.py` is the GO gate. It scores V3 against two
baselines on a holdout the model never trained on and exits nonzero on failure.

- **Holdout:** 2018-2021 trade seasons, n=1100, chosen because those windows have
  fully realized 3-year outcomes.
- **Train:** pre-2018, n=1874. The split is explicit rather than reusing the
  production fit's 2010-2022 range, so the comparators cannot leak.
- **Outcome:** `war_delta`.

| Model | MAE | CRPS | Cov90 | P(direction) |
|---|---|---|---|---|
| Null (train mean) | 1.242 | | | 37.2% |
| Marcel linear | 1.400 | | | 37.0% |
| **V3 (posterior mean)** | **0.892** | 0.995 | 80.5% | 36.5% |

V3 beats the null by 28.2% MAE and Marcel by 36.3%. Verdict: **GO**, gated on
beating both baselines and holding 90% coverage at or above 80%.

Two things worth noticing in that table. Marcel is *worse* than predicting the
training mean, which is what a signal-to-noise ratio of roughly 20:1 does to a
naive linear projection. And directional accuracy sits near 37% for all three
models, including V3: the model is calibrated on magnitude but is not a
sign-prediction machine. It is honest about that rather than tuned to look good
on it.

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
