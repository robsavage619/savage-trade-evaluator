# scripts/

One-off and repeatable scripts, grouped by role. Everything runs as
`uv run python scripts/<name>.py` against the DuckDB store.

## Product / validation (repeatable — keep working)

| Script | Role |
|---|---|
| `v2_full_backtest.py` | The real smoke test: calibration + credible-feature counts across all 4 outcomes |
| `benchmark_vs_naive.py` | D-51 GO decision: V3 vs naïve $/WAR baseline |
| `case_studies.py` | Phase 4 case-study writeups from the production fit |
| `export_warroom.py`, `export_farm.py`, `export_seed.py`, `export_player_profiles.py`, `export_player_index.py`, `export_org_profiles.py`, `export_model_posteriors.py` | Frontend data exporters (JSON payloads consumed by the War Room UI) |
| `v2_smoke_test.py` | Lighter v2 sanity check (v2 archived; superseded by `v2_full_backtest.py`) |

## Data pipeline utilities (repeatable)

| Script | Role |
|---|---|
| `parse_fg_prospects.py` | FanGraphs The Board scrape → `prospect_rankings` |
| `calibrate_prospect_fv.py` | C4 prospect FV→WAR calibration |
| `build_gm_profiles.py` | Phase 3 GM behavioral profiles |
| `refresh_rosters.py` | Roster snapshot refresh from MLB Stats API |
| `rebuild_spotrac_matches.py` | Contract ↔ player ID re-matching |
| `enrich_player_war.py` | Player WAR enrichment pass |
| `probe_data_sources.py` | Availability probe for candidate stat sources |

## Numbered research rounds (`r33`–`r62` — historical, one-off)

Each `rNN_*.py` backs an entry in [`RESEARCH_LOG.md`](../RESEARCH_LOG.md)
(R-33 … R-62) and a decision in the ADR log. They are kept for
reproducibility of the published findings, not maintained as product code.

## Ablations & exploratory analyses (historical, one-off)

`ablation_*.py`, `origin_org_*.py`, `explore_*.py`, `dev_credit_*.py`,
`sell_high_vs_system_tax.py`, `org_stability_decade_split.py`,
`all_regimes_ranked.py`, `cross_metric_pairwise.py`,
`regime_control_reruns.py`, `investigate_regime_anomalies.py`,
`discover_theses.py`, `three_term_demo.py`, `q01_q02_q07_experiments.py`,
`rate_surplus_baseline.py` — feature ablations and thesis explorations
feeding the research log. Same status as the numbered rounds.
