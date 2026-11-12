import flagsJson from '../data/model/contract_flags.json'

type Raw = {
  g?: number
  o?: { s: number; t: string | null; v: number | null; f: string | null }
  c?: 'absent_from_bref' | 'option_inside_window'
  il?: string
  ly?: number
}

const data = flagsJson as unknown as {
  contracts_as_of: string
  roster_as_of: string | null
  players: Record<string, Raw>
}

/** Snapshot dates behind the flags, so a stale flag can be seen to be stale. */
export const flagsAsOf = { contracts: data.contracts_as_of, roster: data.roster_as_of?.slice(0, 10) ?? 'unknown' }

export type Flag = {
  tone: 'warn' | 'info'
  label: string
  detail: string
  /** True when the forecast cannot see this and it can change the answer. */
  blindSpot: boolean
}

const money = (v: number | null) => (v == null ? '' : v >= 1e6 ? `$${+(v / 1e6).toFixed(1)}M` : `$${Math.round(v / 1e3)}K`)
const IL_LABEL: Record<string, string> = { D60: '60-day', D15: '15-day', D10: '10-day', D7: '7-day' }
const LONG_DEAL_THROUGH = 2030

export function flagsFor(id: number): Flag[] {
  const f = data.players[String(id)]
  if (!f) return []
  const out: Flag[] = []
  if (f.c === 'absent_from_bref') {
    out.push({
      tone: 'warn',
      label: 'Not on a club contract page',
      detail:
        `Spotrac shows a multi-year deal, but no club's Baseball-Reference contract page lists him (${data.contracts_as_of}). ` +
        'Likely a free agent: option declined or released. Check before valuing.',
      blindSpot: true,
    })
  }
  if (f.o) {
    const type = f.o.t ?? 'other'
    const playerSide = type === 'player' || type === 'mutual'
    out.push({
      tone: playerSide ? 'warn' : 'info',
      label: `${type[0].toUpperCase()}${type.slice(1)} option ${f.o.s}`,
      detail:
        `${money(f.o.v)} if exercised${f.o.f ? `; ${f.o.f === 'FA' ? 'free agent' : f.o.f} if declined` : ''}. ` +
        (playerSide ? 'The player can leave: the forecast assumes he stays.' : 'The club decides.'),
      blindSpot: playerSide,
    })
  }
  if (f.g) {
    const long = f.g >= LONG_DEAL_THROUGH
    out.push({
      tone: 'info',
      label: `Guaranteed thru ${f.g}`,
      detail:
        `Baseball-Reference contracts as of ${data.contracts_as_of}.` +
        (long ? ' The forecast prices him like a typical veteran, which understates how long he is held.' : ''),
      blindSpot: long,
    })
  }
  if (f.il) {
    out.push({
      tone: 'warn',
      label: `IL ${IL_LABEL[f.il] ?? f.il}`,
      detail: `Injured-list status in the ${data.roster_as_of?.slice(0, 10) ?? 'seed'} roster snapshot. The forecast does not see injuries.`,
      blindSpot: true,
    })
  }
  if (f.ly) {
    out.push({
      tone: 'warn',
      label: `No MLB WAR since ${f.ly}`,
      detail: 'His recent-WAR rate comes from seasons before a long absence.',
      blindSpot: true,
    })
  }
  return out
}

/** The flags that can change the answer, by player, for the players in a trade. */
export function blindSpots(players: readonly { mlb_player_id: number; name: string }[]) {
  return players
    .map(p => ({ name: p.name, flags: flagsFor(p.mlb_player_id).filter(f => f.blindSpot) }))
    .filter(p => p.flags.length > 0)
}
