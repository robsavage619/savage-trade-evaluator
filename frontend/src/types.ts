export type TradeLeg = {
  trade_event_id: number
  leg_index: number
  date: string
  trade_season: number
  mlb_player_id: number
  player_name: string
  from_team_id: number
  from_team_bref: string
  from_team_name: string
  to_team_id: number
  to_team_bref: string
  to_team_name: string
  description: string
}

export type WarWindow = {
  trade_event_id: number
  leg_index: number
  mlb_player_id: number
  player_name: string
  from_team_bref: string
  to_team_bref: string
  war_t_minus_1: number | null
  war_t_total: number | null
  war_t_with_receiver: number | null
  war_t_plus_1: number | null
  war_t_plus_2: number | null
  war_t_plus_3: number | null
}

export type ArsenalWindow = {
  trade_event_id: number
  leg_index: number
  mlb_player_id: number
  player_name: string
  from_team_bref: string
  to_team_bref: string
  fb_velocity_t_minus_1: number | null
  fb_velocity_t_plus_1: number | null
  fb_spin_t_minus_1: number | null
  fb_spin_t_plus_1: number | null
  curve_spin_t_minus_1: number | null
  curve_spin_t_plus_1: number | null
  k_percent_t_minus_1: number | null
  k_percent_t_plus_1: number | null
  bb_percent_t_minus_1: number | null
  bb_percent_t_plus_1: number | null
  whiff_percent_t_minus_1: number | null
  whiff_percent_t_plus_1: number | null
  chase_percent_t_minus_1: number | null
  chase_percent_t_plus_1: number | null
}

export type PitchMovement = {
  trade_event_id: number
  leg_index: number
  mlb_player_id: number
  player_name: string
  from_team_bref: string
  to_team_bref: string
  pitch_type: string
  speed_t_minus_1: number | null
  speed_t_plus_1: number | null
  vert_break_t_minus_1: number | null
  vert_break_t_plus_1: number | null
  horiz_break_t_minus_1: number | null
  horiz_break_t_plus_1: number | null
  usage_t_minus_1: number | null
  usage_t_plus_1: number | null
}

export type Person = {
  mlb_player_id: number
  full_name: string
  birth_date: string | null
  primary_position_name: string | null
  primary_position_code: string | null
  bat_side: string | null
  pitch_hand: string | null
  height_inches: number | null
  weight_lbs: number | null
  birth_country: string | null
  mlb_debut_date: string | null
}

export type Coach = {
  team_id: number
  team_bref: string
  season: number
  job_code: string
  job_title: string | null
  person_name: string
}

export type FrontOffice = {
  team_bref: string
  role: string
  person_name: string
}

export type CareerWar = {
  mlb_player_id: number
  year: number
  team_id: string
  war: number | null
  salary: number | null
}

export type NaiveBaseline = {
  trade_event_id: number
  trade_season: number
  outcome_window_years: number
  team_bref: string
  war_received: number
  war_given_up: number
  surplus: number
  players_received: string
  players_given_up: string
}

export type TradeBundle = {
  trade_event_id: number
  trade_season: number
  trade_date: string
  teams: string[]
  legs: TradeLeg[]
  war_window: WarWindow[]
  arsenal_window: ArsenalWindow[]
  pitch_movement_window: PitchMovement[]
  demographics: Record<string, unknown>[]
  naive_baseline: NaiveBaseline[]
  people: Person[]
  coaches: Coach[]
  front_office: FrontOffice[]
  career_war_pitching: CareerWar[]
  career_war_batting: CareerWar[]
}

export type OrgLandscape = {
  dev: Array<{ team_bref: string; team_name: string; dev_war_total: number; dev_war_avg: number }>
  trade_results: Array<{ team_bref: string; mean_surplus_3yr: number; n_trades: number }>
}

export type GmRegime = {
  gm_name: string
  team_bref: string
  n_trades: number
  mean_surplus: number
  mean_war_received: number
  mean_war_given_up: number
  first_season: number
  last_season: number
}

export type KpctPoint = {
  trade_event_id: number
  mlb_player_id: number
  player_name: string
  from_team_bref: string
  to_team_bref: string
  trade_season: number
  k_percent_t_minus_1: number
  k_percent_t_plus_1: number
  k_delta: number
}
