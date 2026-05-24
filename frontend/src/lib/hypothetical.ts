import type { CurrentPlayer, CurrentTeam } from '../data/players'
import { forecastArb } from './arbForecast'

/** Open-market $/WAR — mirrors arbForecast.ts constant. */
export const MARKET_RATE = 8_500_000

// ── prospect support ──────────────────────────────────────────────────────────

export type ProspectEntry = {
  name: string
  fvGrade: 40 | 45 | 50 | 55 | 60 | 70 | 80
}

/**
 * Expected WAR contribution over a 3-year window for each FV grade.
 *
 * Methodology: start from the commonly cited "career-peak WAR" per FV grade,
 * then apply a ~35% bust-weighted haircut (per Longenhagen/Law hit-rate data
 * showing ~30-40% bust rates at most grades). Treats the 3yr window as the
 * relevant horizon for a trade evaluation, assuming a typical 1–2yr path to
 * the majors for most traded prospects.
 *
 * Grade definitions (FanGraphs convention):
 *  80 FV → elite prospect, probable star               → peak ~5 WAR → EV 3.2
 *  70 FV → top prospect, likely above-average regular  → peak ~4 WAR → EV 2.6
 *  60 FV → solid prospect, above-average likely        → peak ~3 WAR → EV 2.0
 *  55 FV → good prospect, regular with upside          → peak ~2 WAR → EV 1.3
 *  50 FV → average prospect, avg contributor possible  → peak ~1.2 WAR → EV 0.8
 *  45 FV → org depth / fringe MLB                      → peak ~0.5 WAR → EV 0.3
 *  40 FV → long shot, below-average if reaches MLB     → peak ~0.1 WAR → EV 0.06
 *
 * Limitation: no prospect timing model — assumes average proximity to majors.
 * Do not use for prospects explicitly flagged as 3+ years away.
 */
const FV_TO_WAR: Record<number, number> = {
  80: 3.2,
  70: 2.6,
  60: 2.0,
  55: 1.3,
  50: 0.8,
  45: 0.3,
  40: 0.06,
}

export function fvToWar(fv: number): number {
  return FV_TO_WAR[fv] ?? 0.3
}

// ── aging curve ───────────────────────────────────────────────────────────────

/**
 * Year-over-year WAR delta by age bucket.
 *
 * Based on the delta-method aging curve literature (Tango, FanGraphs, BP):
 *  - Peak age: 26–27 (not 28 — the "27.2" consensus from delta-method studies)
 *  - Decline begins at 28 and accelerates past 30
 *  - The 0.5 WAR/yr rule-of-thumb after age 30 includes injury/attrition;
 *    pure aging decline is ~0.2–0.35/yr for healthy players
 *
 * These are unconditional projections (include injury risk implicitly).
 */
export function agingDelta(age: number): number {
  if (age < 24) return 0.15   // development phase, still improving
  if (age < 26) return 0.08   // approaching peak
  if (age < 28) return 0.0    // peak (26–27)
  if (age < 30) return -0.15  // early decline
  if (age < 33) return -0.25  // accelerating decline
  return -0.35                // steep late-career attrition
}

/**
 * Apply team development-system advantage *only* to the incremental upside
 * for players still in the development window.
 *
 * The dev multiplier is a prospective edge — it cannot retroactively inflate
 * observed production. By the time a player reaches 29, he has typically
 * 4–5 years of MLB service and the org's coaching adjustments are fully
 * absorbed. Scale linearly: full advantage at ≤ 23, zero at ≥ 29.
 *
 * Cutoff at 29 (not 30) aligns with the peak-age literature showing
 * development effects plateau by the late-27/early-28 transition. The linear
 * decay is a simplification; an empirical backtest would sharpen the shape.
 */
export function devAdjust(war: number, age: number, devMul: number): number {
  const devScale = Math.max(0, Math.min(1, (29 - age) / 6))
  return war * (1.0 + (devMul - 1.0) * devScale)
}

/**
 * Sum year-over-year surplus WAR net of projected salary over a 3-year window.
 *
 * Correct unit alignment:
 *  - WAR side: aging-curve projected, dev-adjusted *future* production
 *  - Cost side: forecastArb per-year projections[t] for each calendar year
 *
 * Replaces the old `last_war * devMul * 2.6` scalar which conflated
 * observed-season WAR with a 3yr projection and used a fabricated multiplier.
 */
function projectedSurplus3yr(p: CurrentPlayer, devMul: number): number {
  const baseWar = Math.max(0, p.last_war ?? 0.5)
  const age = p.age ?? 28
  const arb = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)

  let total = 0
  let currentWar = baseWar
  for (let t = 0; t < 3; t++) {
    // Advance WAR by one aging step each year
    currentWar = Math.max(0, currentWar + agingDelta(age + t))
    const adjWar = devAdjust(currentWar, age + t, devMul)
    total += adjWar - arb.projections[t] / MARKET_RATE
  }
  return total
}

// ── types ─────────────────────────────────────────────────────────────────────

export type Basket = {
  team: CurrentTeam
  players: CurrentPlayer[]
  prospects?: ProspectEntry[]
}

export type Verdict = {
  surplusMean: number
  surplusSd: number
  surplusLo: number
  surplusHi: number
  pPositive: number
  warSent: number
  warReceived: number
  acquirerDevMultiplier: number
  costSent: number
  costReceived: number
  extensionEstReceived: number
  /** surplusMean × MARKET_RATE — single dollar-value signal. */
  netValueDollars: number
  deadlinePremiumApplied: boolean
  recommendation: 'strong-buy' | 'lean-buy' | 'neutral' | 'lean-pass' | 'strong-pass'
  recommendationLabel: string
  reasoningTone: 'pos' | 'neutral' | 'neg'
}

export type VerdictContext = {
  yourPosture?: 'buy' | 'hold' | 'sell'
  playoffProb?: number
  currentW?: number
  currentL?: number
  gamesBack?: number
}

/** Hand-tuned proxies for receiving-team dev signature. Reproduces the README
 *  finding direction; replaced by V2 model output when the backend lands. */
export const DEV_SIGNATURE: Record<string, number> = {
  HOU: 1.18,
  TBR: 1.15,
  LAD: 1.13,
  CLE: 1.12,
  NYY: 1.1,
  SEA: 1.09,
  STL: 1.08,
  ATL: 1.08,
  MIL: 1.07,
  TOR: 1.06,
  BAL: 1.05,
  NYM: 1.04,
  PHI: 1.04,
  ARI: 1.03,
  SDP: 1.02,
  BOS: 1.0,
  SFG: 0.93,
  MIN: 0.98,
  KCR: 0.97,
  TEX: 0.97,
  CHC: 0.99,
  CIN: 0.97,
  WSN: 0.96,
  DET: 0.96,
  PIT: 0.95,
  CHW: 0.94,
  MIA: 0.94,
  LAA: 0.93,
  OAK: 0.93,
  COL: 0.92,
}

export function computeVerdict(
  { sending, receiving }: { sending: Basket; receiving: Basket },
  context?: VerdictContext,
): Verdict | null {
  const hasPlayers = sending.players.length > 0 || receiving.players.length > 0
  const hasProspects = (sending.prospects?.length ?? 0) > 0 || (receiving.prospects?.length ?? 0) > 0
  if (!hasPlayers && !hasProspects) return null

  const yourDevMul = DEV_SIGNATURE[sending.team.bref] ?? 1.0
  const partnerDevMul = DEV_SIGNATURE[receiving.team.bref] ?? 1.0

  // Raw WAR for display — dev-adjusted at age but NOT the surplus calc basis
  const warSent = sending.players.reduce(
    (a, p) => a + devAdjust(Math.max(0, p.last_war ?? 0.5), p.age ?? 28, partnerDevMul), 0,
  )
  const warReceived = receiving.players.reduce(
    (a, p) => a + devAdjust(Math.max(0, p.last_war ?? 0.5), p.age ?? 28, yourDevMul), 0,
  )

  // 3yr surplus sums via year-by-year aging + dev-adjusted model (Issue 1 + 2 fix)
  const surplusReceived = receiving.players.reduce(
    (a, p) => a + projectedSurplus3yr(p, yourDevMul), 0,
  )
  const surplusSent = sending.players.reduce(
    (a, p) => a + projectedSurplus3yr(p, partnerDevMul), 0,
  )

  // Prospect surplus: FV→WAR EV (bust-weighted) × dev-adjusted at age 22
  // Treated as a lump 3yr contribution since arrival timing is uncertain
  const prospectSurplusReceived = (receiving.prospects ?? []).reduce(
    (a, q) => a + devAdjust(fvToWar(q.fvGrade), 22, yourDevMul), 0,
  )
  const prospectSurplusSent = (sending.prospects ?? []).reduce(
    (a, q) => a + devAdjust(fvToWar(q.fvGrade), 22, partnerDevMul), 0,
  )

  // Deadline premium: buyers pay above surplus WAR for playoff probability uplift.
  // The clearing price for rental talent in July includes option value on a
  // playoff appearance that the off-season surplus model does not capture.
  //
  // Coefficient 0.15 is a calibration parameter — no published study has
  // regressed rental premiums against playoff probability directly. At prob=0.70
  // this produces a ~10.5% premium on received surplus; at the 0.35 floor,
  // ~5.25%. These are conservative relative to observed overpays but avoid
  // over-fitting to noisy trade data. Treat as a tunable dial, not ground truth.
  const prob = context?.playoffProb ?? 0
  const deadlinePremiumApplied = context?.yourPosture === 'buy' && prob > 0.35
  const deadlineMul = deadlinePremiumApplied ? 1.0 + prob * 0.15 : 1.0

  const netReceived = (surplusReceived + prospectSurplusReceived) * deadlineMul
  const netSent = surplusSent + prospectSurplusSent
  const surplusMean = netReceived - netSent

  const totalItems = sending.players.length + receiving.players.length
    + (sending.prospects?.length ?? 0) + (receiving.prospects?.length ?? 0)
  const surplusSd = Math.max(0.8, Math.sqrt(Math.max(1, totalItems)) * 1.2)

  const surplusLo = surplusMean - 1.645 * surplusSd
  const surplusHi = surplusMean + 1.645 * surplusSd

  const z = surplusMean / surplusSd
  const pPositive = 0.5 * (1 + erf(z / Math.sqrt(2)))

  const costSent = sending.players.reduce(
    (a, p) => a + forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr).projections[0], 0,
  )
  const costReceived = receiving.players.reduce(
    (a, p) => a + forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr).projections[0], 0,
  )
  // Show extension estimate for controlled players on received side (Issue 5)
  const extensionEstReceived = receiving.players.reduce((a, p) => {
    const arb = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
    return a + (arb.yearsControlled > 0 ? arb.extensionEst3yr : 0)
  }, 0)

  const netValueDollars = surplusMean * MARKET_RATE

  // Posture-conditional recommendations (Issue 4)
  const posture = context?.yourPosture ?? 'hold'
  let rec: Verdict['recommendation'] = 'neutral'
  let recLabel = 'Neutral — close to baseline'
  let tone: Verdict['reasoningTone'] = 'neutral'

  if (surplusMean > 4 && pPositive > 0.78) {
    rec = 'strong-buy'
    recLabel = posture === 'sell'
      ? 'Strong return — significant controlled/prospect assets inbound'
      : 'Strong buy — surplus clears baseline by >4 WAR across 3yr window'
    tone = 'pos'
  } else if (surplusMean > 1.5 && pPositive > 0.65) {
    rec = 'lean-buy'
    recLabel = posture === 'buy' && deadlinePremiumApplied
      ? 'Lean buy — surplus positive; playoff uplift factored into valuation'
      : posture === 'sell'
      ? 'Reasonable return — asset value positive, consider re-scoping for more'
      : 'Lean buy — surplus likely positive, sized correctly'
    tone = 'pos'
  } else if (surplusMean < -4 && pPositive < 0.22) {
    rec = 'strong-pass'
    recLabel = posture === 'buy'
      ? 'Strong pass — overpaying even with deadline premium. Counter or walk.'
      : 'Strong pass — projected loss-tail dominates'
    tone = 'neg'
  } else if (surplusMean < -1.5 && pPositive < 0.35) {
    rec = 'lean-pass'
    recLabel = posture === 'buy' && deadlinePremiumApplied
      ? 'Lean pass — playoff uplift insufficient to bridge the gap. Counter.'
      : 'Lean pass — counter or re-scope'
    tone = 'neg'
  }

  return {
    surplusMean,
    surplusSd,
    surplusLo,
    surplusHi,
    pPositive,
    warSent,
    warReceived,
    acquirerDevMultiplier: yourDevMul,
    costSent,
    costReceived,
    extensionEstReceived,
    netValueDollars,
    deadlinePremiumApplied,
    recommendation: rec,
    recommendationLabel: recLabel,
    reasoningTone: tone,
  }
}

// Abramowitz & Stegun 7.1.26
function erf(x: number): number {
  const sign = x < 0 ? -1 : 1
  const ax = Math.abs(x)
  const a1 = 0.254829592
  const a2 = -0.284496736
  const a3 = 1.421413741
  const a4 = -1.453152027
  const a5 = 1.061405429
  const p = 0.3275911
  const t = 1 / (1 + p * ax)
  const y = 1 - ((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax)
  return sign * y
}
