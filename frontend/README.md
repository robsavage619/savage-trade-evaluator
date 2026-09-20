# Front end

React SPA for the trade evaluator. It runs entirely client-side off JSON
exported from the DuckDB store, so it needs no backend to demo: no database,
no API keys, no server process.

The backing store holds 54 tables, 4.31M rows, and 9,943 trade events
(7,856 of them between MLB-affiliated clubs).

## Routes

| Route | Purpose |
|---|---|
| `/warroom` | War Room: deadline command center, window assessment, payroll, roster shape, AI brief |
| `/model` | Model Valuation: posterior distributions from the V3 fit |
| `/build` | Trade Builder: construct a package, price it from the acquiring club's context |
| `/orgs` | Org Explorer: 2D development-vs-trade-execution scatter across all 30 clubs |
| `/orgs/:bref` | Org Scout: single-org profile, dev trajectory, payroll stack, 40-man |
| `/player/:id` | Player Profile: WAR trajectory, Statcast percentile radar, trade history |
| `/case/pressly` | Case Study: the 2018 Pressly MIN-to-HOU trade reconstructed from raw data |
| `/research` | Research index |
| `/research/:slug` | Single research article |
| `/trade/:id` | Trade Workspace: three-valuation view (current-roster, trade-acquirer, next-FA) |

## Stack

React 19, TypeScript 6, Vite 8, Tailwind 4, Zustand, Framer Motion, Recharts,
d3-scale, lucide-react, React Router 7.

## Data flow

`scripts/export_*.py` (in the repo root) read the DuckDB store and write typed
JSON into `src/data/`. The app hydrates from those fixtures at build time.
There is no runtime API call to the Python side.

## Display rules

- **Distributions, not points.** A projected metric renders as a posterior with
  a 90% CI band (D-13).
- **Label the method.** Anything computed by the TypeScript heuristic rather
  than the Python posterior carries a visible badge saying so. `computeVerdict`
  in `src/lib/hypothetical.ts` returns `method: 'heuristic'` for this reason.
- **Show coverage.** Scenario cards carry an A-to-D data-coverage grade and the
  top-3 feature attributions behind the number.
- **As-of stamps.** Every screen dates its data.

## Run

```bash
npm install
npm run dev          # http://localhost:5173
npm run build        # production
```

## Re-export seed data

```bash
# from repo root
uv run python scripts/export_seed.py
```
