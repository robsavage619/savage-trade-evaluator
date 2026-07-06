# V3.2 Revalidation — baseline

**Git SHA:** `1536b5f`  **Date:** 2026-07-06

## Single-split backtest
Train through 2020, test 2021–2024.

| Outcome | train_n | test_n | MAE | CRPS | 90% coverage | credible_features |
|---|---|---|---|---|---|---|
| war_delta | 2685 | 1292 | 0.5317 | 0.4896 | 87.6% | 2 |
| dollar_surplus | 3578 | 1730 | 6099670.9983 | 5394402.8942 | 85.0% | 12 |
| surplus_wins | 2685 | 1292 | 0.7064 | 0.6437 | 88.8% | 2 |

## Walk-forward CV

| Outcome | n_folds | mean_CRPS | std_CRPS | confirmed_features | exploratory | error |
|---|---|---|---|---|---|---|
| war_delta | 5 | 0.7724 | 0.276 | 1 | no |  |
| dollar_surplus | 5 | 6013074.9461 | 1250797.8109 | 3 | no |  |
| surplus_wins | 5 | 1.0359 | 0.379 | 1 | no |  |

## Acceptance criteria (D-38)

- **Go**: all three outcomes have `coverage_90 >= 0.80` (grade B or better).
- **Stop**: any outcome below 0.80 — do NOT retrain or tweak; record and report.

Coverage grades: A ≥ 0.80, B ≥ 0.60, C ≥ 0.40, D < 0.40 (note: plan uses A≥0.8 threshold; single-split 90% CI should be near 0.90 if well-calibrated).