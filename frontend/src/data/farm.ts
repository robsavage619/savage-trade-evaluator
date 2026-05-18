import farmJson from './seed/current_farm.json'

export type FarmLevel = 'MLB' | 'AAA' | 'AA' | 'A+' | 'A' | 'R'

export type FarmPlayer = {
  mlb_player_id: number
  name: string | null
  age: number | null
  position_abbr: string | null
  position_name: string | null
  position_code: string | null
  bat_side: string | null
  pitch_hand: string | null
  height_inches: number | null
  weight_lbs: number | null
  birth_country: string | null
  is_pitcher: boolean
  team_id: number | null
  team_name: string | null
  team_abbrev: string | null
  level: FarmLevel
  // Trade-tracking fields (added when reassignment differs from 2024 affiliation)
  former_team_name: string | null
  former_parent: string | null
  moved_since_2024: boolean
  top_sport_id: number | null
  top_level: FarmLevel
  // Hitting (2024 stats)
  pa: number | null
  ab: number | null
  hits: number | null
  hr: number | null
  bb: number | null
  k: number | null
  ops_pa_weighted: number | null
  // Pitching (2024 stats)
  ip: number | null
  era_ip_weighted: number | null
}

export type FarmTeam = {
  bref: string
  season: number
  total_players: number
  levels: Record<FarmLevel, FarmPlayer[]>
}

type Payload = {
  generated_at: string
  season: number
  team_count: number
  player_count: number
  unmatched_count: number
  teams: Record<string, FarmTeam>
}

const data = farmJson as unknown as Payload

export const farmSeason = data.season
export const farmGeneratedAt = data.generated_at
export const farmTeams: Record<string, FarmTeam> = data.teams

export function getFarmForOrg(bref: string): FarmTeam | undefined {
  return farmTeams[bref]
}

let _farmById: Map<number, { player: FarmPlayer; parentBref: string }> | null = null

function buildFarmIndex(): Map<number, { player: FarmPlayer; parentBref: string }> {
  if (_farmById) return _farmById
  const m = new Map<number, { player: FarmPlayer; parentBref: string }>()
  for (const [bref, team] of Object.entries(farmTeams)) {
    for (const lv of LEVEL_ORDER) {
      for (const p of team.levels[lv] ?? []) {
        // First write wins; subsequent rows at lower levels are skipped
        // (player is already represented at their primary level)
        if (!m.has(p.mlb_player_id)) m.set(p.mlb_player_id, { player: p, parentBref: bref })
      }
    }
  }
  _farmById = m
  return m
}

export function getFarmPlayer(id: number): { player: FarmPlayer; parentBref: string } | undefined {
  return buildFarmIndex().get(id)
}

// Farm-system display excludes MLB — those players appear in the 40-man table
export const LEVEL_ORDER: Array<FarmLevel> = ['AAA', 'AA', 'A+', 'A', 'R']

export const LEVEL_LABELS: Record<FarmLevel, string> = {
  MLB: 'Major Leagues',
  AAA: 'Triple-A',
  AA: 'Double-A',
  'A+': 'High-A',
  A: 'Single-A',
  R: 'Rookie',
}
