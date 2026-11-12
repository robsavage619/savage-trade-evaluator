import type { CurrentPlayer, CurrentTeam } from '../data/players'
import { LEAN_LABEL, fmtWar, leanOf, structuralAsOf, validationFacts as v, type PackageComparison } from './structuralData'

export function composeHypotheticalPrompt({
  yourTeam,
  partnerTeam,
  sending,
  receiving,
  forecast,
  costIn,
  costOut,
}: {
  yourTeam: CurrentTeam
  partnerTeam: CurrentTeam
  sending: CurrentPlayer[]
  receiving: CurrentPlayer[]
  forecast: PackageComparison
  costIn: number
  costOut: number
}): string {
  const band = (f: { mean: number; p5: number; p95: number }) =>
    `${fmtWar(f.mean)} WAR, 90% band ${fmtWar(f.p5)} to ${fmtWar(f.p95)}`
  const missing = forecast.received.missing + forecast.sent.missing
  const senders = sending
    .map((p) => `  - ${p.name} (${p.position_abbr ?? '—'}, age ${p.age ?? '?'}, ${p.last_war != null ? `${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)} WAR ${p.last_year}` : 'no recent WAR'}, ${p.last_salary != null ? `$${(p.last_salary / 1e6).toFixed(1)}M` : 'arb-eligible/pre-arb'})`)
    .join('\n')
  const receivers = receiving
    .map((p) => `  - ${p.name} (${p.position_abbr ?? '—'}, age ${p.age ?? '?'}, ${p.last_war != null ? `${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)} WAR ${p.last_year}` : 'no recent WAR'}, ${p.last_salary != null ? `$${(p.last_salary / 1e6).toFixed(1)}M` : 'arb-eligible/pre-arb'})`)
    .join('\n')

  return `# Hypothetical Trade — ${yourTeam.bref} ↔ ${partnerTeam.bref}

You are the analytical reasoning layer of the Savage Trade Evaluator. The ${yourTeam.name} front office is workshopping the following hypothetical trade with the ${partnerTeam.name}. Provide a structured analysis from ${yourTeam.bref}'s perspective.

## What the model is, and is not
- The forecast is the WAR each package is expected to earn for ${yourTeam.bref} from this season through T+5, with a full distribution. It comes from a four-feature model: each player's recent WAR (3-2-1 weighted), the seasons of team control he has left, whether he has MLB history, and the size of the package.
- Tested on ${v.holdout} trades it never saw (${v.nSides.toLocaleString()} sides): the 90% band held ${v.coverage}% of outcomes and beat a constant guess by ${v.crpsGain}% on CRPS. The side with the higher forecast won ${v.favouredWin}% ± ${v.favouredHalf} of ${v.favouredTrades} two-sided trades, so the sign is a lean, not a call.
- NOT in the model: contract length and options (a long guaranteed deal is priced like a typical veteran; a rental or opt-out candidate is priced as if he stays) and injury status, so check both by hand; club context (contention window, payroll, farm depth, dev-system signature: tested, no detectable effect), roster displacement (suggestive, not established), prospects, injuries, and salary. WAR is gross; the salary figures below are data, not netted out. Do not claim the model captures any of these.

## Trade structure

**${yourTeam.name} sends:**
${senders || '  (no players selected)'}

**${yourTeam.name} receives:**
${receivers || '  (no players selected)'}

## Model forecast (${structuralAsOf.note || `priced as of ${structuralAsOf.date}`})
- WAR received: ${band(forecast.received)}
- WAR sent: ${band(forecast.sent)}
- Net for ${yourTeam.bref}: ${band(forecast.net)}; P(receive side ahead) ${(forecast.net.pPositive * 100).toFixed(0)}%
- Year-1 salary received: $${(costIn / 1e6).toFixed(1)}M · sent: $${(costOut / 1e6).toFixed(1)}M
- Forecast read: ${LEAN_LABEL[leanOf(forecast.net)]}${missing > 0 ? `\n- ${missing} player(s) are not in the model export and were left out.` : ''}

## Your task

Produce a JSON object matching the schema below. Output ONLY a single fenced \`\`\`json block.

\`\`\`json
{
  "headline": "Single sharp sentence from ${yourTeam.bref}'s perspective. <= 200 chars.",
  "thesis": "One paragraph stating the core analytical claim. 3-5 sentences. Anchor it in the forecast numbers above and say plainly what the model cannot see.",
  "keyDrivers": [
    { "chip": "Short label", "title": "4-8 word title", "body": "2-3 sentences grounded in the numbers above, or flagged as outside the model." }
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
