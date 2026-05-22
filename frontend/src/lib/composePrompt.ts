import type { TradeBundle } from '../types'
import type { PipelineEntry } from '../data/pipeline'

/** Builds the prompt the user pastes into Claude Code. Includes all
 *  trade-relevant context the model needs to produce reasoning, plus a strict
 *  output schema. */
export function composeClaudePrompt(trade: TradeBundle, pipeline: PipelineEntry): string {
  const [teamA, teamB] = trade.teams
  const naiveByTeam: Record<string, { war_received: number; war_given_up: number; surplus: number } | undefined> = {}
  for (const nb of trade.naive_baseline) naiveByTeam[nb.team_bref] = nb

  // Trade structure
  const legs = trade.legs
    .map((l) => `  - ${l.player_name} (id ${l.mlb_player_id}): ${l.from_team_bref} → ${l.to_team_bref}`)
    .join('\n')

  // WAR window per player
  const warRows = trade.war_window
    .map((w) => {
      const t1 = w.war_t_plus_1 ?? null
      const t2 = w.war_t_plus_2 ?? null
      const t3 = w.war_t_plus_3 ?? null
      const tm1 = w.war_t_minus_1 ?? null
      const tot = (t1 ?? 0) + (t2 ?? 0) + (t3 ?? 0)
      return `  - ${w.player_name}: T-1=${fmt(tm1)} | T+1=${fmt(t1)} | T+2=${fmt(t2)} | T+3=${fmt(t3)} | 3yr sum=${fmt(tot)} WAR`
    })
    .join('\n')

  // Arsenal (only pitchers with data)
  const arsenalRows = trade.arsenal_window
    .filter((a) => a.k_percent_t_minus_1 != null)
    .map(
      (a) =>
        `  - ${a.player_name}: K% ${fmt(a.k_percent_t_minus_1)}→${fmt(a.k_percent_t_plus_1)} | Whiff% ${fmt(a.whiff_percent_t_minus_1)}→${fmt(a.whiff_percent_t_plus_1)} | Chase% ${fmt(a.chase_percent_t_minus_1)}→${fmt(a.chase_percent_t_plus_1)} | BB% ${fmt(a.bb_percent_t_minus_1)}→${fmt(a.bb_percent_t_plus_1)} | FB-spin ${fmt(a.fb_spin_t_minus_1)}→${fmt(a.fb_spin_t_plus_1)} | Curve-spin ${fmt(a.curve_spin_t_minus_1)}→${fmt(a.curve_spin_t_plus_1)} (percentile ranks)`,
    )
    .join('\n')

  // Pitch movement
  const pitchRows = trade.pitch_movement_window
    .map(
      (p) =>
        `  - ${p.player_name} · ${p.pitch_type}: velo ${fmt(p.speed_t_minus_1)}→${fmt(p.speed_t_plus_1)} mph | vert ${fmt(p.vert_break_t_minus_1)}→${fmt(p.vert_break_t_plus_1)}" | horiz ${fmt(p.horiz_break_t_minus_1)}→${fmt(p.horiz_break_t_plus_1)}" | usage ${pct(p.usage_t_minus_1)}→${pct(p.usage_t_plus_1)}`,
    )
    .join('\n')

  // Personnel for each team
  const personnel = trade.teams
    .map((team) => {
      const fo = trade.front_office
        .filter((f) => f.team_bref === team)
        .map((f) => `    - ${f.role}: ${f.person_name}`)
        .join('\n')
      const coach = trade.coaches
        .filter((c) => c.team_bref === team && ['MNGR', 'COAP', 'COAT', 'COAB'].includes(c.job_code))
        .map((c) => `    - ${c.job_title}: ${c.person_name}`)
        .join('\n')
      return `  ${team}:\n${fo}\n${coach}`
    })
    .join('\n\n')

  // Naive baseline
  const naive = trade.naive_baseline
    .map(
      (n) =>
        `  - ${n.team_bref}: received=${fmt(n.war_received)} WAR | given=${fmt(n.war_given_up)} WAR | naive surplus=${signed(n.surplus)} WAR (3-yr window)`,
    )
    .join('\n')

  // Context chips
  const context = pipeline.contextChips.map((c) => `  - ${c.label}: ${c.value}${c.sub ? ` — ${c.sub}` : ''}`).join('\n')

  const acquirer = pipeline.primaryAcquirer
  const sender = pipeline.primarySender

  return `# Trade Reasoning Request — ${pipeline.shortLabel}

You are the analytical reasoning layer of the Savage Trade Evaluator (STE), a context-aware MLB trade-valuation tool. Produce a structured analysis for the front office on the trade below.

## Modeling principles (from project ADR log)
- **D-09 (three-valuation framework):** every player has three valuations — current-roster, trade-acquirer, next-FA-acquirer. The trade-acquirer column is conditioned on the receiving team's contention window, payroll headroom, farm depth, positional need, and dev-system signature.
- **D-11 (naive baseline):** the $/WAR coefficient is the explicit benchmark to beat. Treat as the null hypothesis.
- **D-13 (posterior outputs):** all projections are distributions, not points. When you cite a value, you may include "[mean ±sd]" notation if it sharpens the analysis.
- **D-27 (pitcher K%-trajectory):** confirmed finding — pre-trade K%-trajectory is the strongest single predictor of post-trade K% delta (coef ≈ −10.8, 90% CI [−17.1, −4.3]).
- **MVP Machine ch. 9:** the canonical "Strom intake meeting" thesis — receiving-team analytics/dev infrastructure can flip an arsenal-utilization gap into surplus production.

## Trade context

**Date:** ${trade.trade_date}
**Teams:** ${teamA} ↔ ${teamB}
**Primary acquirer:** ${acquirer}
**Primary sender:** ${sender}

### Player legs
${legs}

### Realized WAR windows (bWAR — Baseball Reference)
${warRows}

### Statcast arsenal — pitchers (pre vs T+1 percentile ranks)
${arsenalRows || '  (no qualified pitchers with Statcast coverage)'}

### Pitch movement (mph and inches; usage as decimal share)
${pitchRows || '  (no pitch-movement data)'}

### Personnel (trade-season)
${personnel}

### Naive $/WAR baseline (3-yr window)
${naive}

### Receiving-team context features (${acquirer})
${context}

## Your task

Produce a JSON object that conforms exactly to the schema below. The app will paste it back into the Reasoning panel. Do NOT include prose outside the JSON code block. Output ONLY a single fenced \`\`\`json block.

\`\`\`json
{
  "headline": "Single sharp sentence — the front-office takeaway. <= 200 chars.",
  "thesis": "One paragraph stating the core analytical claim. Reference 1-2 ADRs (D-09, D-11, D-13, D-27) or the dev signature when it sharpens the argument. 3-5 sentences.",
  "keyDrivers": [
    {
      "chip": "Short label (e.g. '+8.2 K% pp' or 'Cost-controlled')",
      "title": "Driver title — 4-8 words",
      "body": "2-3 sentence explanation grounded in the numbers above."
    }
  ],
  "watchOuts": [
    { "title": "Risk title", "body": "1-2 sentence concrete risk." }
  ],
  "recommendation": "Single clear action — 'Recommend close', 'Recommend pass', 'Counter at X', etc.",
  "citations": [
    { "label": "Source name (e.g. 'D-09 · Three-valuation framework')", "detail": "One-line description." }
  ],
  "modelMeta": {
    "model": "claude-opus-4-7",
    "contextWindow": "1M",
    "latencyMs": 0,
    "promptTokens": 0,
    "outputTokens": 0
  }
}
\`\`\`

Be direct, numbers-first, and skeptical of the naive baseline where context warrants. 3-4 key drivers and 2-3 watch-outs is the right shape.`
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}
function pct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${(v * 100).toFixed(1)}%`
}
function signed(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}`
}
