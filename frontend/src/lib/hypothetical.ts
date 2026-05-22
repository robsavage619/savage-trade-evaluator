import type { CurrentPlayer, CurrentTeam } from '../data/players'

export type Basket = {
  team: CurrentTeam
  players: CurrentPlayer[]
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
  recommendation: 'strong-buy' | 'lean-buy' | 'neutral' | 'lean-pass' | 'strong-pass'
  recommendationLabel: string
  reasoningTone: 'pos' | 'neutral' | 'neg'
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

/** Sum WAR proxy: last-season WAR; defaults to 0.5 (replacement+) when null. */
function warOf(p: CurrentPlayer): number {
  return p.last_war ?? 0.5
}

function salaryOf(p: CurrentPlayer): number {
  // Default salary for unknown: $1.5M (~ pre-arb minimum-ish)
  return p.last_salary ?? 1_500_000
}

export function computeVerdict({ sending, receiving }: { sending: Basket; receiving: Basket }): Verdict | null {
  if (sending.players.length === 0 && receiving.players.length === 0) return null

  const warSent = sending.players.reduce((a, p) => a + warOf(p), 0)
  const warReceived = receiving.players.reduce((a, p) => a + warOf(p), 0)

  // `sending.team` is YOU (the player-source for your outgoing basket = your team).
  // `receiving.team` is your trade PARTNER. Players you receive enter your dev
  // system; players you send enter the partner's dev system.
  const yourDevMul = DEV_SIGNATURE[sending.team.bref] ?? 1.0
  const partnerDevMul = DEV_SIGNATURE[receiving.team.bref] ?? 1.0

  const adjReceived = warReceived * yourDevMul
  const adjSent = warSent * partnerDevMul

  // Net surplus, projected over ~3yr window (multiply by 2.6 because last-WAR is single-season)
  const surplusMean = (adjReceived - adjSent) * 2.6

  // SD scales with squareroot of player count (uncertainty per player ≈ 1.0 WAR over 3yr)
  const totalPlayers = sending.players.length + receiving.players.length
  const surplusSd = Math.max(0.7, Math.sqrt(totalPlayers) * 1.1)

  const surplusLo = surplusMean - 1.645 * surplusSd
  const surplusHi = surplusMean + 1.645 * surplusSd

  // P(positive) via normal approximation
  const z = surplusMean / surplusSd
  const pPositive = 0.5 * (1 + erf(z / Math.sqrt(2)))

  const costSent = sending.players.reduce((a, p) => a + salaryOf(p), 0)
  const costReceived = receiving.players.reduce((a, p) => a + salaryOf(p), 0)

  let rec: Verdict['recommendation'] = 'neutral'
  let recLabel = 'Neutral — close to baseline'
  let tone: Verdict['reasoningTone'] = 'neutral'
  if (surplusMean > 4 && pPositive > 0.78) {
    rec = 'strong-buy'
    recLabel = 'Strong buy — context-aware posterior clears baseline by >4 WAR'
    tone = 'pos'
  } else if (surplusMean > 1.5 && pPositive > 0.65) {
    rec = 'lean-buy'
    recLabel = 'Lean buy — surplus likely positive, sized correctly'
    tone = 'pos'
  } else if (surplusMean < -4 && pPositive < 0.22) {
    rec = 'strong-pass'
    recLabel = 'Strong pass — projected loss-tail dominates'
    tone = 'neg'
  } else if (surplusMean < -1.5 && pPositive < 0.35) {
    rec = 'lean-pass'
    recLabel = 'Lean pass — counter or re-scope'
    tone = 'neg'
  }

  return {
    surplusMean,
    surplusSd,
    surplusLo,
    surplusHi,
    pPositive,
    warSent: adjSent,
    warReceived: adjReceived,
    acquirerDevMultiplier: yourDevMul,
    costSent,
    costReceived,
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
