import type { OrgProfile } from '../data/orgs'

/** Build a scout-brief prompt the user pastes into Claude Code. Produces a
 *  structured 1-pager AiReasoning JSON aimed at the "scout this org for a
 *  potential trade partner" workflow. */
export function composeOrgScoutPrompt({ profile, teamName, yourBref }: { profile: OrgProfile; teamName: string; yourBref: string }): string {
  const last3 = profile.trajectory.slice(-3)
  const trajLine = last3.map((r) => `${r.season}: ${r.wins}-${r.losses}${r.war_total != null ? ` (${r.war_total.toFixed(1)} WAR)` : ''}`).join(' · ')
  const dev = profile.dev_signature
  const trade = profile.trade_dna.summary
  const recentTrades = profile.trade_dna.recent
    .slice(0, 6)
    .map((t) => `  - ${t.trade_season}: received ${t.players_received || '—'} for ${t.players_given_up || '—'} (surplus ${t.surplus >= 0 ? '+' : ''}${t.surplus.toFixed(2)} WAR)`)
    .join('\n')

  const fo = profile.fo_history
    .filter((f) => f.season === Math.max(...profile.fo_history.map((x) => x.season)))
    .map((f) => `  - ${f.role}: ${f.person_name}`)
    .join('\n')

  const payroll = profile.payroll.top_contracts
    .slice(0, 5)
    .map((p) => `  - ${p.name_common} (${p.role}): $${((p.salary ?? 0) / 1e6).toFixed(1)}M${p.war != null ? ` · ${p.war >= 0 ? '+' : ''}${p.war.toFixed(1)} WAR` : ''}`)
    .join('\n')

  return `# Org Scouting Brief — ${profile.bref} (${teamName})

You are the analytical reasoning layer of the Savage Trade Evaluator. The ${yourBref} front office is preparing to engage ${profile.bref} on potential trades. Produce a structured scouting brief that the GM will read before picking up the phone.

## Modeling principles
- **D-09 (three-valuation framework):** every player has current-roster, trade-acquirer, next-FA-acquirer value. ${profile.bref}'s dev signature directly affects acquirer-column value for players THEY receive.
- **D-11 (naive baseline):** $/WAR is the benchmark. Their mean trade surplus tells you whether their GM beats it.
- **D-27 (K%-trajectory):** pre-trade K%-trajectory predicts post-trade delta; dev signature amplifies or dampens.

## Org snapshot — ${profile.bref}

**3-yr trajectory:** ${trajLine}

**Dev signature (last 5 yr):**
- Pitcher K%-jump norm: ${dev.avg_pitcher_k_jump_3yr != null ? `${dev.avg_pitcher_k_jump_3yr.toFixed(1)} pp` : 'n/a'}
- Hitter xwOBA-jump norm: ${dev.avg_hitter_xwoba_jump_3yr != null ? dev.avg_hitter_xwoba_jump_3yr.toFixed(3) : 'n/a'}

**Trade DNA (3-yr surplus window):**
${trade ? `- n trades: ${trade.n_trades} · mean surplus: ${(trade.mean_surplus ?? 0).toFixed(2)} WAR · positive rate: ${trade.n_positive}/${trade.n_trades} (${((trade.n_positive ?? 0) / (trade.n_trades || 1) * 100).toFixed(0)}%)\n- min ${(trade.min_surplus ?? 0).toFixed(2)} · max ${(trade.max_surplus ?? 0).toFixed(2)}` : '- no trade-history record'}

**Recent trades:**
${recentTrades || '  (none in DB)'}

**Top contracts (last ingested season):**
${payroll || '  (no payroll data)'}

**Front office:**
${fo || '  (no FO record)'}

## Your task

Output ONLY a single fenced \`\`\`json block matching this schema:

\`\`\`json
{
  "headline": "Single sharp sentence — what ${yourBref} needs to know about ${profile.bref} before calling. <= 200 chars.",
  "thesis": "One paragraph (3-5 sentences) on this org's posture, leverage points, and where you'd expect to find trade value with them.",
  "keyDrivers": [
    { "chip": "Short label", "title": "Driver title 4-8 words", "body": "2-3 sentence body grounded in the snapshot above." }
  ],
  "watchOuts": [
    { "title": "Risk title", "body": "1-2 sentence concrete risk when transacting with this org." }
  ],
  "recommendation": "Single line — 'Target X-profile players', 'Avoid dealing for Y', 'Approach about Z', etc.",
  "citations": [
    { "label": "Source name", "detail": "One-line description." }
  ],
  "modelMeta": { "model": "claude-opus-4-7", "contextWindow": "1M", "latencyMs": 0, "promptTokens": 0, "outputTokens": 0 }
}
\`\`\`

Be direct and numbers-first. 3-4 key drivers, 2-3 watch-outs. Frame from ${yourBref}'s side.`
}
