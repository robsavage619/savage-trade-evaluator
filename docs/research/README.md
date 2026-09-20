# Research log

Twenty-six rounds of experiments, run May 2026. Each round states a question,
the setup, the measured result, what it implies, and which decisions it moves.
The log is append-only: entries are superseded by later rounds, never rewritten.

The headline: the thesis this project started with was rejected. Rounds R-30 and
R-31 found that young players gain WAR after a trade regardless of which
organization they leave, which is the opposite of the predicted system tax.
What survived is in `docs/PHASE1_SYNTHESIS.md`.

## Rounds

| Round | Date | Finding | Part |
|---|---|---|---|
| **R-01** | 2026-05-15 | Phase 2 V0 naive baseline backtest against realized-WAR ground truth | [1](part-1-baseline-and-first-ablations.md) |
| **R-02** | 2026-05-15 | OLS 3-feature fit fails to beat predict-zero | [1](part-1-baseline-and-first-ablations.md) |
| **R-03** | 2026-05-15 | Bayesian 3-feature fit. Calibrated posterior within 1% CRPS of predict-zero | [1](part-1-baseline-and-first-ablations.md) |
| **R-04** | 2026-05-15 | OLS catastrophically overfits with 5 features; Bayesian holds | [1](part-1-baseline-and-first-ablations.md) |
| **R-05** | 2026-05-15 | Phase 3 V0. Pitcher dev-fit feature beats predict-zero (first win) | [1](part-1-baseline-and-first-ablations.md) |
| **R-06** | 2026-05-16 | Hitter dev-fit ablation. Feature contributes ~0 on the matched subset | [1](part-1-baseline-and-first-ablations.md) |
| **R-07** | 2026-05-16 | Per-coach hitter operationalization. Also ~0 contribution | [1](part-1-baseline-and-first-ablations.md) |
| **R-08-prep** | 2026-05-16 | Future Value methodology ingested. Prospect-feature design candidates surfaced | [1](part-1-baseline-and-first-ablations.md) |
| **R-09** | 2026-05-16 | Draft pedigree feature null at V1 scale | [1](part-1-baseline-and-first-ablations.md) |
| **R-10** | 2026-05-16 | Origin-org system-tax test. The LAD signal collapses 25x under controls; NYM and HOU are big... | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-11** | 2026-05-16 | Retrosheet pre-2010 transaction ingest. 2.5x affiliated-trade sample expansion | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-12** | 2026-05-16 | WAR-version of origin-org system-tax test on R-11 expanded sample | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-13** | 2026-05-16 | Age-conditioned WAR-version test. Population effects unchanged, but pairwise posterior frami... | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-14** | 2026-05-16 | Analytics-leader-cluster feature. Null predictive contribution, redundant with team-cluster ... | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-15** | 2026-05-16 | Per-player dev-signature feature. First ablation with positive directional signal | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-16** | 2026-05-16 | Pitcher K%-based origin-org test. Only HOU survives cross-metric replication | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-17** | 2026-05-16 | Cross-metric pairwise replication of R-13. LAD < HOU and LAD < CLE both hold | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-18** | 2026-05-16 | Acquired-player age and WAR-trajectory features. Modest directional signal, but the trajecto... | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-19** | 2026-05-16 | First credibly-real coefficients. Switching from a WAR-surplus outcome to a rate-based xwOBA... | [2](part-2-origin-org-and-the-metric-correction.md) |
| **R-20/21/22/23** | 2026-05-16 | omnibus four-outcome ablation. R-22 surfaces the largest credible coefficient in the entire ... | [3](part-3-omnibus-ablations-and-regime-control.md) |
| **R-25** | 2026-05-16 | Org-stability decade-split. GM regimes drive 90% of within-team variance; org-identity-as-fe... | [3](part-3-omnibus-ablations-and-regime-control.md) |
| **R-26** | 2026-05-16 | Statcast-extended ingest. Batter percentile ranks, pitcher arsenal stats, OAA | [3](part-3-omnibus-ablations-and-regime-control.md) |
| **R-27** | 2026-05-16 | Regime-control reruns. Most R-17 findings weaken; OAK-Beane emerges as the strongest specifi... | [3](part-3-omnibus-ablations-and-regime-control.md) |
| **R-30** | 2026-05-16 | Sell-high vs system-tax decomposition. The original Dodgers thesis is rejected; TEX-Daniels ... | [4](part-4-decomposition-dev-credit-and-fortification.md) |
| **R-31** | 2026-05-16 | Dev-credit attribution. Built the org-quality 2D map, found surprising rankings, debunked th... | [4](part-4-decomposition-dev-credit-and-fortification.md) |
| **R-32** | 2026-05-17 | Data-fortification arc. 10 new sources, schema v11 to v19, real ages and birth countries fin... | [4](part-4-decomposition-dev-credit-and-fortification.md) |

## Parts

- [Baseline and first ablations (R-01 to R-09)](part-1-baseline-and-first-ablations.md)
  Establishing a predict-zero baseline, finding that OLS overfits where a Bayesian
- [Origin-org tests and the metric correction (R-10 to R-19)](part-2-origin-org-and-the-metric-correction.md)
  The arc that broke the original thesis. R-10 collapses the raw LAD signal 25x
- [Omnibus ablations and regime control (R-20 to R-27)](part-3-omnibus-ablations-and-regime-control.md)
  Four outcomes tested at once, which surfaces R-22, the largest credible
- [Decomposition, dev credit, and data fortification (R-30 to R-32)](part-4-decomposition-dev-credit-and-fortification.md)
  Separating sell-high from system-tax, which rejects the original thesis outright.

## Gaps

R-21, R-23, and R-24 have no standalone entry: R-21 to R-23 are written up inside
the R-20/21/22/23 omnibus, and R-24 was setup work folded into R-26. R-28 and R-29
are referenced by R-30 but were never written up on their own.

Rounds R-33 onward were never written up here at all. They exist as
`scripts/rNN_*.py` with their printed output as the record, and as decisions in
the ADR log. R-33, R-34, and R-35 are the important ones: together they found the
multilevel (team, regime) structure added no predictive signal over a flat model,
which is why V3 dropped it.

## Entry format

```markdown
## [YYYY-MM-DD] R-NN: Short title

**Question.** What we wanted to learn.
**Setup.** Data subset / features / model / seed / train-test split.
**Result.** Metrics. Reference scripts/<file>.py or commit hash.
**Interpretation.** What this means and confidence level.
**Affects.** D-NN entries supported or refined, and follow-up R-NN candidates.
```

Related, and deliberately separate:

- `LESSONS.md`: infrastructure gotchas that generalize.
- `trade-eval--decisions.md` (vault): D-NN decisions, what we chose and why.
- `CHANGELOG.md`: shipped features per commit.
