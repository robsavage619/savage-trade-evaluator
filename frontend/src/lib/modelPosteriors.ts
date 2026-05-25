import raw from '../data/model/posteriors.json'

export type PosteriorSummary = {
  mean: number
  sd: number
  p05: number
  p25: number
  p50: number
  p75: number
  p95: number
  draws: number[]
}

export type ModelCard = {
  trade_event_id: number
  receiver_bref: string
  sender_bref: string | null
  season: number
  role: 'covered' | 'tail_miss'
  acquired_players: string[]
  posterior: PosteriorSummary
  realized: number
  realized_in_90ci: boolean
}

export type ModelScoreboard = {
  train_n: number
  test_n: number
  crps: number
  coverage_90: number
  mae: number
}

export type CredibleFeature = {
  feature: string
  beta: number
  directional_mass: number
}

export type ComparisonFold = {
  label: string
  n_test: number
  crps_context: number
  crps_quality: number
  crps_intercept: number
  skill_vs_quality: number
  skill_vs_intercept: number
  structural_break: boolean
}

export type ModelComparison = {
  folds: ComparisonFold[]
  mean_skill_vs_quality: number
  mean_skill_vs_intercept: number
  mean_skill_vs_quality_ex_break: number
  mean_skill_vs_intercept_ex_break: number
}

export type ModelPosteriors = {
  generated_at: string
  outcome: string
  unit: string
  train_window: [number, number]
  test_window: [number, number]
  scoreboard: ModelScoreboard
  comparison: ModelComparison
  credible_features: CredibleFeature[]
  cards: ModelCard[]
}

export const modelPosteriors = raw as ModelPosteriors

/** Human-readable feature labels for the "what the model weighted" panel. */
export const FEATURE_LABELS: Record<string, string> = {
  receiver_acquired_player_quality: 'Acquired-player quality (T-1 WAR tier)',
  receiver_pct_international_born: 'Acquired share intl-born',
  receiver_acquired_milb_hit_quality: 'Acquired MiLB hit quality',
  receiver_acquired_player_avg_war_trajectory: 'Acquired WAR trajectory',
  receiver_acquired_pct_awarded: 'Acquired share award-winning',
  receiver_acquired_milb_age_advantage: 'Acquired MiLB age advantage',
  receiver_dev_fit_hitting: 'Receiving-org hitting dev-fit',
  receiver_org_pitcher_k_jump_3yr: 'Receiving-org pitcher K-jump (3yr)',
}

export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature
}
