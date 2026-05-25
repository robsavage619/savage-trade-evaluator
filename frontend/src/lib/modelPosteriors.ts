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
  // wins headline (surplus_wins)
  wins_posterior: PosteriorSummary | null
  wins_realized: number | null
  wins_realized_in_90ci: boolean | null
  // dollar anchor (dollar_surplus)
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
  wins_crps: number
  wins_coverage_90: number
  wins_mae: number
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
  wins_outcome: string
  unit: string
  wins_unit: string
  train_window: [number, number]
  test_window: [number, number]
  scoreboard: ModelScoreboard
  comparison: ModelComparison
  wins_comparison: ModelComparison
  credible_features: CredibleFeature[]
  cards: ModelCard[]
}

export const modelPosteriors = raw as ModelPosteriors

/** Human-readable feature labels for the "what the model weighted" panel. */
export const FEATURE_LABELS: Record<string, string> = {
  // V3 credible features (directional mass >= 0.95)
  receiver_acquired_player_quality: "Acquired player quality (prior-season WAR)",
  receiver_pct_pitchers: "Acquired share who are pitchers",
  receiver_avg_age_at_trade: "Average age of acquired players at trade",
  receiver_acquired_from_dev_cluster_score: "Origin org development quality",
  receiver_acquired_pitcher_k_trajectory: "Acquired pitcher strikeout trend",
  receiver_dev_fit_hitting: "Receiving team hitter-development track record",
  // Other features that may appear
  receiver_pct_international_born: "Acquired share internationally-born",
  receiver_acquired_milb_hit_quality: "Acquired hitters minor-league quality",
  receiver_acquired_player_avg_war_trajectory: "Acquired player WAR trend",
  receiver_acquired_pct_awarded: "Acquired share with prior awards",
  receiver_acquired_milb_age_advantage: "Acquired players young for their level",
  receiver_org_pitcher_k_jump_3yr: "Receiving team pitcher strikeout gains (3yr)",
  receiver_acquired_avg_fv: "Acquired prospect avg FV grade (FanGraphs)",
  receiver_acquired_max_fv: "Top acquired prospect FV grade (FanGraphs)",
}

export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature
}

/** Compact per-trade posterior (no embedded draws — Gaussian, so mean/sd suffice). */
export type TradePosterior = {
  season: number
  split: 'in_sample' | 'held_out'
  // wins headline (surplus_wins)
  wins_mean: number | null
  wins_sd: number | null
  wins_p05: number | null
  wins_p50: number | null
  wins_p95: number | null
  wins_realized: number | null
  wins_realized_in_90ci: boolean | null
  // dollar anchor (dollar_surplus)
  mean: number
  sd: number
  p05: number
  p50: number
  p95: number
  realized: number
  realized_in_90ci: boolean
  acquired_players: string[]
  sender_bref: string | null
}

type ByTradePayload = {
  by_trade: Record<string, TradePosterior>
}

let _byTrade: Record<string, TradePosterior> | null = null

/** Lazy-load the 5k-entry per-trade posterior lookup (1.2MB) — only the Trade
 *  Workspace needs it, so it stays out of the main bundle. */
export async function loadTradePosterior(
  tradeEventId: number,
  receiverBref: string,
): Promise<TradePosterior | null> {
  if (_byTrade == null) {
    const mod = (await import('../data/model/by_trade.json')) as { default: ByTradePayload }
    _byTrade = mod.default.by_trade
  }
  return _byTrade[`${tradeEventId}:${receiverBref}`] ?? null
}
