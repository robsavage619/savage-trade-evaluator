# Savage Trade Evaluator — Front-End Wireframe

Premium-feel React wireframe for a context-aware MLB trade-valuation tool, pitched at MLB baseball-operations analytics teams. Pairs with the `savage-trade-evaluator` Python backend (DuckDB · 27 tables · 1.29M rows · 9.4K trade events 2010-2024).

## Three screens

| Route | Purpose |
|---|---|
| `/case/pressly` | Onboarding hero — 5-station scrollytelling of the canonical Pressly MIN→HOU 2018 case |
| `/trade/:id` | Trade Workspace — three-valuation centerpiece (current-roster · trade-acquirer · next-FA) with personnel triangle, context inputs, and as-of audit |
| `/orgs` | Org Explorer — 2D dev-vs-trade scatter, GM regime rankings, pitcher K%-trajectory finding |

## Stack
React 18 · Vite · TypeScript · Tailwind v4 · Framer Motion · Recharts · d3-scale · lucide-react · React Router

## Data flow
- **Phase 1 (current):** `scripts/export_seed.py` (in repo root) reads from the real DuckDB and writes typed JSON to `src/data/seed/`. The app hydrates from those fixtures at build time.
- **Phase 2 (planned):** FastAPI backend serving the same view shapes; swap the seed loader for fetch calls — no UI changes.

## Design principles
- **Distribution-native** — every projected metric appears as a posterior violin with a 90% CI band, never a bare point estimate (per D-13).
- **Honesty UI** — every screen shows an "as-of" date stamp; audit panels surface the no-leakage guarantee (D-10).
- **Bloomberg-density** — numerics-dense, monospace tabular figures, Linear/Vercel-tier dark palette.
- **Premium without flash** — Framer Motion transitions are subtle and purposeful.

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
