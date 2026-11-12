import type { CurrentPlayer } from '../data/players'

/** Open-market $/WAR — league blended, for headline dollar display only. */
export const MARKET_RATE = 8_500_000

/**
 * Effective position for pricing: seed pitchers carry a bare 'P', which the arb
 * model would mistype as a starter. The enrichment's is_reliever flag corrects
 * relievers to 'RP' so both salary projection and the $/WAR rate match the
 * canonical value_player (reliever $6M/WAR vs starter $7.2M).
 */
export function effectivePos(p: CurrentPlayer): string | null {
  if (p.is_reliever) return 'RP'
  return p.position_abbr
}

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

/**
 * True-talent WAR base for valuation: the calibrated Python projection
 * (regressed + leverage-adjusted, from scripts/enrich_player_projection.py) when
 * present, else raw last-season WAR. This is what feeds the aging/dev/arb layers
 * below — the trade-workshop keeps its dev-system edge and deadline premium, but
 * on a base that no longer extrapolates a hot partial season.
 */
export function baseWar(p: CurrentPlayer): number {
  return Math.max(0, p.valued_war ?? p.last_war ?? 0.5)
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

// ── types ─────────────────────────────────────────────────────────────────────

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
