# Naïve Baseline Evaluator — Design

The model we explicitly want to beat. Derived from Nate Silver's "Is Alex Rodriguez Overpaid?" framework ([BBtN Ch 5-2](../../../Vault/savage_vault/wiki/click-keri-2006-ch5-2-is-arod-overpaid.md)). Single global $/WAR coefficient, no context-aware terms.

This module is the **explicit benchmark for every future model.** Any context-aware extension must beat the naïve baseline on out-of-time backtest calibration. If it doesn't, the extension is noise.

## Surplus value definition

For one trade *event*:

```
surplus_value(trade) = sum over receiving-side players of:
                           (realized_war_post_trade - implied_war_at_trade_price) * $_per_war
                     - sum over giving-side players of: same
```

where:
- `realized_war_post_trade` = sum of `war_t_with_receiver` + `war_t_plus_1` + ... + `war_t_plus_N` for each player going to that team. Window length N is Q-02 (likely 3yr primary, 5yr robustness).
- `implied_war_at_trade_price` = remaining contract dollars / $_per_war coefficient
- `$_per_war` = 2024-dollar-adjusted FA market price per WAR (≈ $8M/WAR in current FA market; will be re-derived from our data)

The naïve baseline uses **one global `$_per_war` coefficient** for all team-context, all eras (after inflation adjustment), all positions. **That is exactly the assumption the context-aware thesis (D-01) is built to violate.**

## Inputs

All from existing V1 data layer:

| Input | Source |
|---|---|
| Trade structure | `trade_player_unified` |
| Realized WAR per player per year | `trade_player_war_window` |
| Player salary at trade time | `bwar_batting.salary` / `bwar_pitching.salary` |
| Contract remaining years | not in V1 yet — placeholder until Cot's adapter exists |
| $/WAR for the era | hard-coded table from BBtN ch5-2 calibration; refresh quarterly |

## Module layout

```
src/savage_trade_evaluator/
├── modeling/
│   ├── __init__.py
│   ├── naive_baseline.py     # the model
│   └── dollars_per_war.py    # the $/WAR table + era-adjustment helpers
└── analysis/
    └── backtest.py           # run the model over every trade, compute residuals
```

## API sketch

```python
from savage_trade_evaluator.modeling import naive_baseline

# evaluate one trade event
result = naive_baseline.evaluate(trade_event_id=371509, outcome_window_years=3)
# returns:
#   TradeEvaluation(
#       trade_event_id=371509,
#       receiving_team_surplus={117: 6.27, 142: -1.86},  # HOU gained 6.27 WAR-equiv
#       implied_value_at_trade={117: ..., 142: ...},
#       realized_value_post_trade={117: ..., 142: ...},
#       per_leg_breakdown=[...],
#   )

# run the backtest over the whole 2010-2024 corpus
report = backtest.run(start_season=2010, end_season=2024, outcome_window_years=3)
# returns a DataFrame: one row per trade with model_value, realized_value, residual,
# plus aggregate calibration metrics (MAE, CRPS proxy, hit-rate at trade-was-good)
```

## Calibration anchors

From BBtN ch5-2:

| Period | $/Marginal Win (Silver 2005 estimate) |
|---|---|
| Linear model (regular-season-only) | ≈ $1.196M gross, ≈ $1M net |
| FA-market revealed | ≈ $1.75M (50% premium over linear) |
| Two-tiered (regular + playoff bump) | $705K/win + $14.9M per playoff appearance |

These are 2005 dollars. For 2024 we need to re-derive — MLB revenue has roughly tripled since 2005. As a starting placeholder use ~$8M/WAR in 2024 dollars, then **re-derive from our own panel regression as Phase 1.5 work**.

## What this model is bad at (and what we use it for)

The naïve baseline is *deliberately* bad at:

1. **Context-dependence.** Pressly to HOU 2018 = same value as Pressly to KCR 2018 in this model. The model can't see the dev-system gap.
2. **Variance.** Point estimate only, no posterior. D-13 says we want distributions — naïve gives means.
3. **Cost-control structure.** Treats year-1 of a cost-controlled contract identically to year-1 of a FA contract.
4. **Postseason nonlinearity.** Linear $/WAR with no playoff bump. BBtN ch5-2 has the two-tiered version; we'll add later.
5. **Selection on gains.** Ignores the Mixtape ch4 ATT vs ATE distinction. Treats trades as randomly assigned.

These are exactly the gaps the **context-aware model is built to close.** The baseline's failure modes are the V2 model's research agenda.

## Phase-1 deliverable

A Jupyter notebook (or script) that:

1. Loads `trade_player_war_window` for all 2010-2024 trades
2. Computes naïve surplus for every trade event
3. Ranks the biggest model errors (cases where realized ≫ predicted or ≪ predicted)
4. Categorizes the error patterns (dev-fit wins, FA-bust losses, prospect-bust losses, etc.) → those become V2 model features

Per the planning brief's Phase 1 deliverable spec: *"a Jupyter notebook / report ranking the biggest model errors and looking for patterns. These patterns are the features for V2."*

## Open questions to settle before implementation

- **Q-01** (trade scope cutoff): for now apply the model to *every* trade event. Filter when characterizing residuals — Q-01 then drops out from the residual distribution shape.
- **Q-02** (outcome window): run with both 3yr and 5yr windows; compare which separates the residual signal more cleanly.
- **Q-07** (transition cost): expose two variants of T@rcv handling — (a) include trade-year T@rcv WAR, (b) start outcome window at T+1. Compare residual distributions.

The naïve baseline becomes the *experimental harness* for closing these three open questions, not just a benchmark.
