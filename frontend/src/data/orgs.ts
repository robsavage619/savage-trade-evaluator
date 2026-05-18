import profiles from './seed/org_profiles.json'

export type TrajectoryPoint = {
  season: number
  wins: number | null
  losses: number | null
  win_pct: number | null
  war_total: number | null
  runs_scored: number | null
  runs_allowed: number | null
}

export type DevSignature = {
  avg_pitcher_k_jump_3yr: number | null
  avg_hitter_xwoba_jump_3yr: number | null
  history: Array<{
    season: number
    prior_year_war: number | null
    org_pitcher_k_jump_3yr: number | null
    org_hitter_xwoba_jump_3yr: number | null
    org_dev_fit_pitching: number | null
    org_dev_fit_hitting: number | null
    farm_war_top_10: number | null
  }>
}

export type TradeRow = {
  trade_event_id: number
  trade_season: number
  players_received: string | null
  players_given_up: string | null
  war_received: number
  war_given_up: number
  surplus: number
  description: string
}

export type TradeDna = {
  recent: TradeRow[]
  summary: {
    n_trades: number | null
    mean_surplus: number | null
    mean_received: number | null
    mean_given: number | null
    n_positive: number | null
    min_surplus: number | null
    max_surplus: number | null
  } | null
}

export type FoEntry = { season: number; role: string; person_name: string }
export type Coach = { season: number; job_code: string; job_title: string | null; person_name: string }

export type PayrollTopRow = {
  mlb_id: number
  name_common: string
  role: 'P' | 'B'
  war: number | null
  salary: number | null
}

export type AgeCurveRow = {
  mlb_id: number
  full_name: string
  birth_date: string | null
  war: number
  role: 'P' | 'B'
  position_code: string | null
  age: number | null
}

export type SpotracPayrollRow = {
  season: number
  active_players: number | null
  active_payroll: number | null
  dead_money: number | null
  injured_payroll: number | null
  total_payroll: number | null
}

export type ContractBreakdownRow = {
  status: string
  n: number
  total_cap: number | null
  avg_svc: number | null
}

export type OrgProfile = {
  bref: string
  trajectory: TrajectoryPoint[]
  dev_signature: DevSignature
  spotrac_payroll: SpotracPayrollRow[]
  contract_breakdown: ContractBreakdownRow[]
  trade_dna: TradeDna
  fo_history: FoEntry[]
  coaches: Coach[]
  coach_season: number | null
  payroll: { season: number | null; top_contracts: PayrollTopRow[] }
  age_curve: AgeCurveRow[]
  org_placement: { dev_war: number | null; mean_surplus: number | null; n_trades: number | null } | null
}

type ProfilesPayload = { generated_at: string; teams: Record<string, OrgProfile> }

const data = profiles as unknown as ProfilesPayload

export const orgProfiles: Record<string, OrgProfile> = data.teams
export const orgProfilesGeneratedAt = data.generated_at

export function getOrgProfile(bref: string): OrgProfile | undefined {
  return orgProfiles[bref]
}
