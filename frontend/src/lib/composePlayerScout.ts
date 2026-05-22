import type { PlayerProfile } from '../data/playerTypes'
import type { CompResult } from './comps'

export function composePlayerScoutPrompt({
  profile,
  teamBref,
  yourBref,
  comps,
}: {
  profile: PlayerProfile
  teamBref: string | null
  yourBref: string
  comps: CompResult[]
}): string {
  const bio = profile.bio
  const isPitcher = profile.is_pitcher
  const career = isPitcher ? profile.career.pitching : profile.career.batting
  const careerWar = career.reduce((a, r) => a + (r.war ?? 0), 0)
  const recent = [...career].sort((a, b) => b.year - a.year).slice(0, 5)
  const recentLines = recent
    .map((r) => `  - ${r.year}: ${(r.war ?? 0).toFixed(1)} WAR${r.salary != null ? ` · $${(r.salary / 1e6).toFixed(1)}M` : ''}`)
    .join('\n')

  const latestPct = isPitcher ? profile.percentiles.pitching[profile.percentiles.pitching.length - 1] : profile.percentiles.batting[profile.percentiles.batting.length - 1]
  const fpLines = latestPct
    ? Object.entries(latestPct)
        .filter(([k, v]) => k !== 'year' && typeof v === 'number')
        .map(([k, v]) => `  - ${k}: ${v}`)
        .join('\n')
    : '  (no Statcast fingerprint available)'

  const arsenalLines = profile.arsenal.length
    ? Object.values(
        profile.arsenal.reduce<Record<string, typeof profile.arsenal[number]>>((acc, a) => {
          if (!acc[a.pitch_type] || (acc[a.pitch_type].year ?? 0) < a.year) acc[a.pitch_type] = a
          return acc
        }, {}),
      )
        .map((a) => `  - ${a.pitch_name ?? a.pitch_type}: usage ${(a.pitch_usage ?? 0).toFixed(1)}% · K% ${(a.k_percent ?? 0).toFixed(1)} · whiff ${(a.whiff_percent ?? 0).toFixed(1)} · RV/100 ${(a.run_value_per_100 ?? 0).toFixed(1)}`)
        .join('\n')
    : '  (no arsenal data)'

  const compLines = comps
    .slice(0, 5)
    .map((c) => `  - ${c.player.name} (${c.player.team}, age ${c.player.age ?? '?'}, ${c.player.war != null ? `${c.player.war >= 0 ? '+' : ''}${c.player.war.toFixed(1)} WAR` : 'no WAR'}${c.player.salary != null ? ` · $${(c.player.salary / 1e6).toFixed(1)}M` : ''}) · similarity ${c.score.toFixed(0)}`)
    .join('\n')

  const tradeLines = profile.trades
    .slice(-5)
    .map((t) => `  - ${t.trade_date}: ${t.from_team_bref} → ${t.to_team_bref}`)
    .join('\n')

  return `# Player Scouting Workup — ${bio.full_name}

You are the analytical reasoning layer of the Savage Trade Evaluator. The ${yourBref} front office wants a structured scouting workup on this player, framed for a potential acquisition (or for context on whether to target them in a deal).

## Modeling principles
- **D-09 (three-valuation framework):** value depends on which org acquires the player — current-roster, trade-acquirer, next-FA. State your view from ${yourBref}'s acquirer-column perspective.
- **D-13 (posterior outputs):** distribution-native projections; cite uncertainty bands when meaningful.
- **D-27 (K%-trajectory):** pitcher K%-trajectory predicts post-trade K% delta.
- **MVP Machine ch. 9:** receiving-team dev infrastructure can flip arsenal-utilization gaps.

## Subject

**${bio.full_name}** · ${bio.primary_position_name ?? '—'} · ${isPitcher ? 'pitcher' : 'hitter'}
Currently with: ${teamBref ?? 'free agent / unrostered'}
Age: ${bio.birth_date ? Math.max(0, new Date().getFullYear() - new Date(bio.birth_date).getFullYear()) : '?'} · Debut: ${bio.mlb_debut_date ?? '—'}
Hand: ${bio.pitch_hand ?? bio.bat_side ?? '—'}
Career WAR: ${careerWar.toFixed(1)} across ${career.length} season-stints
${bio.height_inches ? `Build: ${Math.floor(bio.height_inches / 12)}'${bio.height_inches % 12}" · ${bio.weight_lbs ?? '?'}lb` : ''}

## Last 5 seasons (bWAR · salary)
${recentLines || '  (no career data)'}

## Statcast fingerprint (latest year — percentile ranks 0-100)
${fpLines}

${isPitcher ? `## Arsenal (latest year per pitch type)
${arsenalLines}` : ''}

## Trade history
${tradeLines || '  (never traded)'}

## League comparables (by position + age + Statcast similarity)
${compLines || '  (no comps available)'}

## Your task

Output ONLY a single fenced \`\`\`json block matching this schema:

\`\`\`json
{
  "headline": "Single sharp sentence from ${yourBref}'s perspective. <= 200 chars.",
  "thesis": "One paragraph (3-5 sentences) on this player's profile, trajectory, and trade-acquirer-column outlook.",
  "keyDrivers": [
    { "chip": "Short label", "title": "Driver title 4-8 words", "body": "2-3 sentence body grounded in the snapshot above." }
  ],
  "watchOuts": [
    { "title": "Risk title", "body": "1-2 sentence concrete risk." }
  ],
  "recommendation": "Single line — 'Target as primary piece', 'Avoid — overpay risk', 'Reasonable secondary piece', etc.",
  "citations": [
    { "label": "Source name", "detail": "One-line description." }
  ],
  "modelMeta": { "model": "claude-opus-4-7", "contextWindow": "1M", "latencyMs": 0, "promptTokens": 0, "outputTokens": 0 }
}
\`\`\`

Be direct and numbers-first. 3-4 key drivers, 2-3 watch-outs. Reference comps when they sharpen the argument.`
}
