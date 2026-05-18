export type PlayerBio = {
  mlb_player_id: number
  full_name: string
  birth_date: string | null
  birth_country: string | null
  height_inches: number | null
  weight_lbs: number | null
  bat_side: string | null
  pitch_hand: string | null
  primary_position_code: string | null
  primary_position_name: string | null
  mlb_debut_date: string | null
  last_played_date: string | null
  active: boolean | null
}

export type CareerBattingRow = {
  year: number
  team_id: string
  war: number | null
  salary: number | null
  g: number | null
  pa: number | null
  runs_above_avg: number | null
  runs_above_avg_off: number | null
  runs_above_avg_def: number | null
}

export type CareerPitchingRow = {
  year: number
  team_id: string
  war: number | null
  salary: number | null
  g: number | null
  gs: number | null
  era_plus: number | null
  ra: number | null
  xra: number | null
  bip: number | null
}

export type PctilePitcherRow = {
  year: number
  xwoba: number | null
  xba: number | null
  xslg: number | null
  brl_percent: number | null
  exit_velocity: number | null
  hard_hit_percent: number | null
  k_percent: number | null
  bb_percent: number | null
  whiff_percent: number | null
  chase_percent: number | null
  fb_velocity: number | null
  fb_spin: number | null
  curve_spin: number | null
  xera: number | null
}

export type PctileBatterRow = {
  year: number
  xwoba: number | null
  xba: number | null
  xslg: number | null
  brl_percent: number | null
  exit_velocity: number | null
  hard_hit_percent: number | null
  k_percent: number | null
  bb_percent: number | null
  whiff_percent: number | null
  chase_percent: number | null
  sprint_speed: number | null
  oaa: number | null
  bat_speed: number | null
  squared_up_rate: number | null
  swing_length: number | null
}

export type ArsenalRow = {
  year: number
  pitch_type: string
  pitch_name: string | null
  pitch_usage: number | null
  k_percent: number | null
  whiff_percent: number | null
  run_value_per_100: number | null
  woba: number | null
  est_woba: number | null
  hard_hit_percent: number | null
}

export type PitchMovementRow = {
  year: number
  pitch_type: string
  pitch_name: string | null
  avg_speed: number | null
  pitch_usage_pct: number | null
  vertical_break_inches: number | null
  horizontal_break_inches: number | null
  induced_vertical: number | null
  percentile_diff_vertical: number | null
  percentile_diff_horizontal: number | null
}

export type TradeRow = {
  trade_event_id: number
  trade_date: string
  from_team_bref: string
  to_team_bref: string
  from_team_name: string | null
  to_team_name: string | null
}

export type AwardRow = {
  season: number
  award_name: string
  team_name: string | null
  votes: number | null
}

export type ContractRow = {
  season: number
  team_bref: string
  status: string | null
  service_time: number | null
  acquired_method: string | null
  base_salary: number | null
  cap_hit: number | null
  signing_bonus: number | null
  position: string | null
}

export type PlayerProfile = {
  bio: PlayerBio
  is_pitcher: boolean
  career: { batting: CareerBattingRow[]; pitching: CareerPitchingRow[] }
  percentiles: { pitching: PctilePitcherRow[]; batting: PctileBatterRow[] }
  expected: { batting: unknown[]; pitching: unknown[] }
  arsenal: ArsenalRow[]
  pitch_movement: PitchMovementRow[]
  trades: TradeRow[]
  awards?: AwardRow[]
  contracts?: ContractRow[]
}

const cache = new Map<number, Promise<PlayerProfile | null>>()

export function loadPlayerProfile(id: number): Promise<PlayerProfile | null> {
  if (!cache.has(id)) {
    cache.set(
      id,
      fetch(`/data/players/${id}.json`)
        .then((r) => (r.ok ? (r.json() as Promise<PlayerProfile>) : null))
        .catch(() => null),
    )
  }
  return cache.get(id)!
}
