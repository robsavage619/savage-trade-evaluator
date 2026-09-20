# Decision drafts: trust and explainability release (2026-07-05)

ADR entries for steps 2 to 11. Append to `~/Vault/savage_vault/wiki/trade-eval--decisions.md` as D-53 through D-56.

---

## D-53: Term-1 salary aggregation fix (2026-07-05)

**Decision:** In `three_term_value.py::compute_cost_controlled_surplus`, dedup salary to one row per
`(mlb_id, season)` using `MAX(salary)` across the `bwar_batting` + `bwar_pitching` UNION ALL, then
`SUM` the deduped rows over the control window. The prior `AVG(salary)` was averaging per-season
salary over a multi-year window, inflating surplus by roughly a factor of N, where N is the window length.

**Impact:** Prior code overstated cost-controlled surplus for multi-year windows. With a 4-year
window and $10M/yr salary, prior output was $10M cost against a correct $40M, a 4x error. The fix also
prevents two-way players from having their salary double-counted (once via batting row, once via
pitching row).

**Known simplification kept:** Full trade-year salary counted to the receiver even though they pay
only the prorated balance of the trade year. This is intentional; exact proration requires
contract-structure data we don't have.

**Empirical calibration deferred.** There is no regression test against ground-truth deal economics:
would require a labeled dataset of historical surplus-vs.-cost outcomes with verified salary figures.

---

## D-54: Era-aware playoff win curve (2026-07-05)

**Decision:** `_playoff_prob(wins, season)` selects curve constants by era:
- Pre-2022: midpoint 89.0, k 0.18 (the prior calibration, calibrated to the 10-team wild-card era)
- 2022+: midpoint 86.0, k 0.18 (12-team expanded playoffs; lower wins threshold for postseason access)

The midpoint shift from 89 to 86 reflects that 12 teams now qualify per league (vs. 10 pre-2022), so
a ~86-win pace sits at the playoff boundary rather than ~89.

**Empirical calibration deferred:** A proper calibration would regress historical playoff
qualification rates against win totals by era, accounting for strength-of-schedule variation.
The 86.0 constant is a principled estimate pending that regression. A qualifier table in the DB
would sharpen this; that ingestion is deferred.

**`evaluate()` threading:** `trade_season` is now passed through from the trade-event query to
the Term-3 calculation so the correct era branch is used for historical trades.

---

## D-55: Predict-time multiple imputation, opt-in, marginal, no-go for production (2026-07-05)

**Decision:** `v3.py::predict` gains `multiple_imputation: bool = False`. When enabled, missing
features for each test row receive per-sample draws from N(0,1) clipped to ±5 (z-space), rather
than the pre-imputation feature mean. This mechanically widens posterior intervals for sparse rows
(rookies, pre-Statcast-era players, players with thin context history).

**Validation outcome (D-38 required):** Part 2 of `docs/revalidation/2026-07-post-mi.md` returned
**NO-GO** for production use. On sparse rows (25% or more of features missing), MI widened intervals as
intended, but CRPS degraded +14.5% (war_delta) and +16.8% (surplus_wins) relative to mean-fill.
Root cause: marginal imputation draws each missing feature independently from its z-marginal,
ignoring correlations (exit velocity and barrel rate, for instance). With 8+ missing Statcast features,
the independent draws amplify noise that correlated draws would cancel.

**Resolution:** `scenario_engine._score_df` reverts to mean-fill imputation. The
`predict(multiple_imputation=True)` API is committed and tested for future use when a conditional
(multivariate-normal) imputation strategy is implemented. MODEL_VERSION stays v3.2; training
untouched; backtest numbers confirmed bit-identical to baseline (Part 1 match).

**Future path:** Conditional imputation using the training covariance matrix of z-space features.
That is a D-38 experiment. It requires a new fit or a separate covariance cache, and a new GO/NO-GO
validation pass.

---

## D-56: Attribution and coverage layer in scenario payloads (2026-07-05)

**Decision:** `scenario_engine.py` gains two metadata layers, added without changing any posterior
computation:

1. **Coverage report** (`coverage_report(features, fit) -> dict`): computed from the pre-imputation
NaN mask restricted to `fit.feature_cols`. Reports n_total, n_observed, n_imputed,
imputed_features list, observed_fraction, and a letter grade (A at 0.8 or above, B at 0.6, C at 0.4, D below that).
Present in every outcome dict under `"coverage"`.

2. **Feature attribution** (`attribute_score(fit, features, top_k=5) -> dict`): standardizes the
feature row identically to `predict()`: clip, subtract means, divide by stds, with NaN mapped to 0
(zero contribution in z-space by construction). Computes `contribution_i = beta_mean_i * x_z_i * y_std`
per feature; returns baseline, top-K signed contributors with observed/imputed flag and credible
flag (CI excludes zero), sum_all, and reconstructed_mean. Present in `war_delta` outcome dict
under `"attribution"`.

**MODEL_VERSION stays v3.2.** Nothing here touches training data, likelihoods, priors, or
sampling parameters. The cached fits are valid and were not retrained.

**Frontend wiring:** TradeWorkshop renders historical ScenarioCards with coverage grade chips
(A=green, B=accent, C=yellow, D=red) and top-3 attribution lines. TradeBuilder and TradeWorkshop
label user-built basket verdicts with a persistent `method: 'heuristic'` badge clarifying that the
uncertainty band is a `sqrt(n) * 1.2` heuristic, not a model posterior.
