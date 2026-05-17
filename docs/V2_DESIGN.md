# V2 Model Design

> **Status:** in active build. Architecture locked in (this doc); implementation under `src/savage_trade_evaluator/modeling/v2/`.

V2 incorporates all five methodology corrections from Phase 1 (D-24/25/26/28/29) plus the data-layer fortification of 2026-05-16/17 (Chadwick, MLB people, Spotrac, Retrosheet game logs, etc.).

## What V2 produces

For any proposed trade `(team_A, team_B, players_A→B, players_B→A)`, V2 outputs **joint posterior distributions** over four outcome metrics per receiving team:

| Outcome | Coverage | Type | Use |
|---|---|---|---|
| Δ xwOBA (3yr) | Statcast era 2015+ | rate-based hitter | quality-of-contact change |
| Δ K%-percentile (3yr) | Statcast era 2015+ | rate-based pitcher | strikeout-rate change (R-22 finding lives here) |
| Δ WAR (3yr cumulative) | 1990+ | aggregate | broad performance signal |
| Δ $-surplus (3yr) | 2011+ | dollar | trade-value bottom line |

Each is its own multilevel Bayesian fit per D-27 (feature importance is outcome-specific). The product surface shows median + 90% CI + per-quartile predictions per outcome.

## Architecture

### Cluster structure (D-28)

Hierarchical with nested partial pooling on (team, regime):

```
alpha[regime] ~ Normal(alpha[team], tau_regime)
alpha[team]   ~ Normal(0, tau_team)
```

Regime IDs come from `team_regime_assignments` (front_office data, now 1990-2024 after the BR backfill). Pre-1990 trades fall back to team-only (per D-28 partial-pooling design).

### Feature backbone — three buckets

All features are within-team-variation per D-24 (no static team-only signals — those failed in R-06/07/09/14).

**1. Acquired-player features** (vary per trade based on who's coming in):

| Feature | Source view |
|---|---|
| acquired_player_avg_age (real, from birth_date) | trade_player_demographics |
| acquired_player_war_trajectory | trade_with_context |
| acquired_player_quality (rate-based) | trade_with_context |
| acquired_pitcher_k_trajectory | trade_with_context (R-22 finding) |
| acquired_pitcher_arsenal_volatility | trade_with_context |
| pct_international_born | trade_receiver_demographic_mix |
| pct_left_handed_bat / pitch | trade_receiver_demographic_mix |
| pct_pitchers | trade_receiver_demographic_mix |
| avg_height_inches / weight_lbs | trade_receiver_demographic_mix |

**2. Receiver-team context** (changes by team and season):

| Feature | Source view |
|---|---|
| prior_year_wins, prior_year_pyth_pct | team_season_features |
| org_dev_fit_pitching, org_dev_fit_hitting | team_season_features |
| org_pitcher_k_jump_3yr, org_hitter_xwoba_jump_3yr | team_season_features |
| total_payroll, dead_money | spotrac_team_payroll (NEW) |
| park_factor_raw | team_season_run_environment (NEW) |

**3. Origin-side features**:

| Feature | Source view |
|---|---|
| origin_regime_intercept_prior | (derived from R-25/R-27/R-30 origin-regime work) |
| origin_team_recent_dev_signature | (derived from trades by origin team in last 3 years) |

### Surplus-value baseline (D-30 candidate, now live)

Replaces the naive flat $8M/WAR baseline with:

```
$_surplus = Σ_{years} [WAR_t × league_$/WAR_t]_received
          − Σ_{years} cap_hit_t_received
          − [same accounting for given-up players, sign-flipped]
```

Sources:
- `WAR` from `bwar_player_seasons` (acquired-player career, post-trade window)
- `league_$/WAR_t` from FA-market reference (hardcoded per season; ~$8M flat early, $9-11M recent)
- `cap_hit_t` from `spotrac_player_contracts`

For V2.0 we hardcode league $/WAR; V2.1 could derive it dynamically from FA-signing data.

### Backtest design

- **Train**: trades 1990-2020 (most legs; ~6,000 affiliated trades)
- **Test**: 2021-2024 (out-of-time, ~1,500 trades)
- **Primary metric**: CRPS on test (lower = better calibration)
- **Secondary**: per-quartile coverage (does the 90% CI actually contain 90% of outcomes?)
- **Smoke test**: calibration ≥ 90% on held-out 2021-2024; ≥1 credible feature per outcome at the D-26 threshold

### Credibility framework (D-26)

A feature is reported as "credibly real" iff its posterior has **90% CI excluding zero AND ≥95% directional mass**. This is the bar that surfaced R-19's three features and R-22's k_trajectory finding.

The V2 backtest report shows every feature's posterior with these flags.

## Module structure

```
src/savage_trade_evaluator/modeling/v2/
├── __init__.py
├── features.py    # build_feature_matrix(start, end) → DataFrame
├── outcomes.py    # build_outcomes(start, end) → DataFrame with 4 target cols
├── regimes.py     # (trade_event, receiver) → (team, regime_id) mapping
├── multilevel.py  # fit_multilevel(features, outcome, clusters) → trace
├── backtest.py    # train_test_split, fit, score, report
└── posterior.py   # convert trace → per-trade prediction distribution
```

CLI:

```bash
uv run ste v2 fit --outcome xwoba --start 2010 --end 2020
uv run ste v2 backtest --outcome xwoba
uv run ste v2 predict --trade-id <event_id>
```

## Build order

1. **features.py + outcomes.py** — assemble the data
2. **regimes.py** — (team, regime) mapping with pre-1990 fallback
3. **multilevel.py** — single-outcome PyMC fit, validate convergence
4. **backtest.py** — train-test split + CRPS + calibration
5. **Distribution smoke test** — coverage ≥ 90% on test set; ≥1 credible feature per outcome
6. **R-33 V2 baseline ablation** — vs V1 on the same data; does V2 add credible features?

## Open follow-ups (V2.1+)

- **Joint vector outcome** instead of four parallel models (captures correlations across metrics)
- **Dynamic league $/WAR** from FA signings (not hardcoded)
- **Arb-eligible / FA-eligible status** as features (from Spotrac `status` field)
- **Pre-trade contract length** (years remaining)
- **Trade-counterparty features** — what is team_B giving up? (currently only team_A's receive-side is modeled)
- **Player-level posterior**, not just team-level (per-acquired-player prediction)

These are all V2.1 candidates. V2.0 ships the four-outcome multilevel + backtest.
