import type { CurrentPlayer, CurrentTeam } from '../data/players'
import type { Verdict } from './hypothetical'

export function composeHypotheticalPrompt({
  yourTeam,
  partnerTeam,
  sending,
  receiving,
  verdict,
}: {
  yourTeam: CurrentTeam
  partnerTeam: CurrentTeam
  sending: CurrentPlayer[]
  receiving: CurrentPlayer[]
  verdict: Verdict
}): string {
  const senders = sending
    .map((p) => `  - ${p.name} (${p.position_abbr ?? '—'}, age ${p.age ?? '?'}, ${p.last_war != null ? `${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)} WAR ${p.last_year}` : 'no recent WAR'}, ${p.last_salary != null ? `$${(p.last_salary / 1e6).toFixed(1)}M` : 'arb-eligible/pre-arb'})`)
    .join('\n')
  const receivers = receiving
    .map((p) => `  - ${p.name} (${p.position_abbr ?? '—'}, age ${p.age ?? '?'}, ${p.last_war != null ? `${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)} WAR ${p.last_year}` : 'no recent WAR'}, ${p.last_salary != null ? `$${(p.last_salary / 1e6).toFixed(1)}M` : 'arb-eligible/pre-arb'})`)
    .join('\n')

  return `# Hypothetical Trade — ${yourTeam.bref} ↔ ${partnerTeam.bref}

You are the analytical reasoning layer of the Savage Trade Evaluator. The ${yourTeam.name} front office is workshopping the following hypothetical trade with the ${partnerTeam.name}. Provide a structured analysis from ${yourTeam.bref}'s perspective.

## Modeling principles (project ADR log)
- **D-09 (three-valuation framework):** every player has current-roster, trade-acquirer, and next-FA-acquirer value. Trade-acquirer column conditions on receiving team's contention window, payroll, farm depth, positional need, dev-system signature.
- **D-11 (naive baseline):** $/WAR coefficient is the explicit benchmark.
- **D-13 (posterior outputs):** distribution-native, not points.
- **D-27 (K%-trajectory):** pitcher K%-trajectory predicts T+1 K% delta (coef ≈ −10.8).
- **MVP Machine ch. 9:** receiving-team dev infrastructure can flip arsenal-utilization gaps.

## Trade structure

**${yourTeam.name} sends:**
${senders || '  (no players selected)'}

**${yourTeam.name} receives:**
${receivers || '  (no players selected)'}

## Model snapshot (synthetic v1)
- Receiving-team dev multiplier (${yourTeam.bref}): ${verdict.acquirerDevMultiplier.toFixed(2)}
- Adjusted WAR sent: ${verdict.warSent.toFixed(2)}
- Adjusted WAR received: ${verdict.warReceived.toFixed(2)}
- 3-yr surplus posterior: mean ${verdict.surplusMean.toFixed(2)} WAR, sd ${verdict.surplusSd.toFixed(2)}, 90% CI [${verdict.surplusLo.toFixed(2)}, ${verdict.surplusHi.toFixed(2)}]
- P(surplus > 0): ${(verdict.pPositive * 100).toFixed(0)}%
- Cost sent: $${(verdict.costSent / 1e6).toFixed(1)}M · Cost received: $${(verdict.costReceived / 1e6).toFixed(1)}M
- Model recommendation: ${verdict.recommendationLabel}

## Your task

Produce a JSON object matching the schema below. Output ONLY a single fenced \`\`\`json block.

\`\`\`json
{
  "headline": "Single sharp sentence from ${yourTeam.bref}'s perspective. <= 200 chars.",
  "thesis": "One paragraph stating the core analytical claim. 3-5 sentences. Reference ADRs (D-09, D-11, D-13, D-27) where they sharpen the argument.",
  "keyDrivers": [
    { "chip": "Short label", "title": "4-8 word title", "body": "2-3 sentences grounded in the numbers above." }
  ],
  "watchOuts": [
    { "title": "Risk title", "body": "1-2 sentence concrete risk." }
  ],
  "recommendation": "Single clear action — 'Recommend close', 'Counter at X', 'Pass', etc.",
  "citations": [
    { "label": "Source name", "detail": "One-line description." }
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

Be direct, numbers-first, and skeptical when warranted. 3-4 key drivers and 2-3 watch-outs is the right shape. Frame everything from ${yourTeam.bref}'s side of the table.`
}
