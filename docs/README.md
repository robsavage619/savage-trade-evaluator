# Documentation

Start with the [project README](../README.md). This index covers what sits
underneath it.

## Current

| Doc | What it covers |
|---|---|
| [architecture.md](architecture.md) | Module layout, the ingest-to-product path, CLI surface, where state lives |
| [evaluation.md](evaluation.md) | How a claim earns the word "credible": benchmark, credibility bar, revalidation protocol |
| [STATS_CATALOG.md](STATS_CATALOG.md) | Every data source, its status, and live row counts. Mirrors `ingest/catalog.py` |
| [NAIVE_BASELINE.md](NAIVE_BASELINE.md) | Design of the $/WAR baseline the model is measured against |
| [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md) | Walk-forward CV rules, confirmation thresholds, what counts as exploratory |
| [PHASE1_SYNTHESIS.md](PHASE1_SYNTHESIS.md) | What survived the research phase and what did not |
| [product-tour.md](product-tour.md) | Screenshots and what each frontend route does |
| [research/](research/README.md) | 26 rounds of experiments, indexed by round and by part |
| [revalidation/](revalidation/) | Committed backtest reports with git SHAs, pass and fail alike |
| [decision-drafts/](decision-drafts/) | ADR entries staged before they move to the vault decision log |

## Archived

Kept because the reasoning still holds, even where the conclusions do not.
Each carries a status header explaining what changed.

| Doc | Why it is archived |
|---|---|
| [archive/V2_DESIGN.md](archive/V2_DESIGN.md) | V2's multilevel structure was measured to add nothing; V3 dropped it |
| [archive/DATA_SOURCE_PROBE.md](archive/DATA_SOURCE_PROBE.md) | Point-in-time source sweep; several blocked verdicts have since been cleared |

## Reading order

Three minutes: the project README.

Twenty minutes: the README, then [architecture.md](architecture.md) for how it
fits together, then [evaluation.md](evaluation.md) for whether to believe any of
it.

An afternoon: add [research/](research/README.md) starting from
[part 2](research/part-2-origin-org-and-the-metric-correction.md), which is where
the original thesis breaks. Then pick a `scripts/rNN_*.py`, read its docstring,
run it, and compare the output to the entry.
