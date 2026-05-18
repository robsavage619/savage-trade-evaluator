import current from './seed/current_players.json'

export type AwardsSummary = {
  all_star: number
  mvp: number
  cy_young: number
  silver_slugger: number
  gold_glove: number
  rookie_of_year: number
  total: number
}

export type CurrentPlayer = {
  mlb_player_id: number
  name: string
  jersey: string | null
  position_code: string | null
  position_abbr: string | null
  position_name: string | null
  status_code: string | null
  status_desc: string | null
  note: string | null
  birth_date: string | null
  age: number | null
  birth_country: string | null
  height: string | null
  weight: number | null
  bat_side: string | null
  pitch_hand: string | null
  mlb_debut_date: string | null
  last_year: number | null
  last_war: number | null
  last_salary: number | null
  // Spotrac contract overlay (latest ingested season)
  spotrac_season: number | null
  contract_status: string | null
  service_time: number | null
  acquired_method: string | null
  cap_hit: number | null
  base_salary_spotrac: number | null
  awards: AwardsSummary | null
}

export type CurrentTeam = {
  bref: string
  mlb_team_id: number
  name: string
  roster_count: number
  players: CurrentPlayer[]
}

export type CurrentRoster = {
  refreshed_at: string
  season_used_for_war: number | null
  team_count: number
  player_count: number
  teams: CurrentTeam[]
}

export const roster = current as unknown as CurrentRoster

export const teamsByBref: Record<string, CurrentTeam> = Object.fromEntries(roster.teams.map((t) => [t.bref, t]))

export function findPlayer(id: number): { player: CurrentPlayer; team: CurrentTeam } | undefined {
  for (const t of roster.teams) {
    const p = t.players.find((x) => x.mlb_player_id === id)
    if (p) return { player: p, team: t }
  }
  return undefined
}

/** Lightweight global search across all teams. */
export function searchPlayers(query: string, opts?: { teamBref?: string; positionGroup?: 'pitcher' | 'hitter' | 'all' }): Array<{ player: CurrentPlayer; team: CurrentTeam }> {
  const q = query.trim().toLowerCase()
  const out: Array<{ player: CurrentPlayer; team: CurrentTeam }> = []
  for (const t of roster.teams) {
    if (opts?.teamBref && t.bref !== opts.teamBref) continue
    for (const p of t.players) {
      if (opts?.positionGroup === 'pitcher' && p.position_code !== '1') continue
      if (opts?.positionGroup === 'hitter' && p.position_code === '1') continue
      if (q) {
        const hay = `${p.name} ${p.jersey ?? ''} ${p.position_abbr ?? ''}`.toLowerCase()
        if (!hay.includes(q)) continue
      }
      out.push({ player: p, team: t })
    }
  }
  return out
}
