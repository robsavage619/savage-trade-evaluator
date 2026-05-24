/**
 * Arbitration salary forecasting.
 *
 * Key improvements over v1:
 *  - Position-split $/WAR: position players ≈ $9.5M, pitchers ≈ $7.5M
 *    (reflects recent arb settlement patterns, not a single league-wide rate)
 *  - Position premium/discount: up-the-middle premium (SS +12%, 2B +8%, CF +8%),
 *    corner discount (1B −10%, DH −10%)
 *  - Projection uncertainty: ±20% pre-arb, ±18% arb1, ±15% arb2/3
 *    (arb panels have more comps as service time increases)
 *  - Offensive vs defensive WAR split approximation: position players with
 *    primary value via defence (SS, CF) get a small bump; corner bats get a discount
 *    (arb panels historically undervalue pure dWAR)
 *
 * Limitations explicitly tracked:
 *  - Comparables-based model deferred to V2 (requires historical arb settlement DB)
 *  - Service time manipulation (April optioning) not modelled
 *  - Contract structure (opt-outs, vesting options) not modelled
 */

/** Current MLB minimum salary (2026 season). */
const MLB_MIN = 740_000

/**
 * Open-market $/WAR by player type, calibrated to 2024–26 free-agent actuals.
 *
 * Source: Paraball Notes 2024/25 market analysis — overall market ~$8M/WAR.
 * Batters trade below starters on a per-WAR basis in recent cycles because
 * positional depth suppresses batter prices at the margin; the batter rate
 * here reflects above-replacement free agents, not the full distribution
 * (which drags the average down to ~$5.7M). Starter rate from ~$6.9M observed,
 * rounded up slightly for 2026 inflation. Reliever remains cheapest per WAR.
 */
const MARKET_RATE: Record<PlayerType, number> = {
  batter: 8_500_000,
  starter: 7_200_000,
  reliever: 6_000_000,
}

/** Fraction of open-market value paid per arb year. */
const ARB_MULTIPLIERS: Record<number, number> = {
  1: 0.40,
  2: 0.60,
  3: 0.80,
}

/** Projection uncertainty (multiplicative half-width of ±1σ band). */
const ARB_UNCERTAINTY: Record<ArbClass, number> = {
  'pre-arb': 0.22,
  arb1: 0.18,
  arb2: 0.15,
  arb3: 0.12,
  fa: 0.10,
}

/** Position premium/discount applied to the arb multiplier.
 *  Based on observed over/under-payment relative to WAR in recent arb cycles. */
const POSITION_PREMIUM: Record<string, number> = {
  SS: 1.12,
  '2B': 1.08,
  CF: 1.08,
  C: 1.06,
  '3B': 1.02,
  RF: 1.00,
  LF: 0.98,
  '1B': 0.90,
  DH: 0.88,
  SP: 1.00,
  RP: 0.95,
  P: 1.00,
}

export type ArbClass = 'pre-arb' | 'arb1' | 'arb2' | 'arb3' | 'fa'
export type PlayerType = 'batter' | 'starter' | 'reliever'

export type ArbForecast = {
  currentClass: ArbClass
  playerType: PlayerType
  /** Point estimates for the next 3 seasons (index 0 = next season). */
  projections: [number, number, number]
  /** Lower bound (−1σ) for each projection. */
  projectionsLo: [number, number, number]
  /** Upper bound (+1σ) for each projection. */
  projectionsHi: [number, number, number]
  /** Seasons of team control remaining. */
  yearsControlled: number
  /** Three-season total projected cost (point estimate). */
  totalCost3yr: number
  /**
   * Estimated market-clearing extension cost over 3 years.
   * Reflects agent leverage: acquiring teams face pressure to lock up
   * controlled studs. Pre-arb agents demand ~65% premium over arb path;
   * premium declines as control years shrink.
   */
  extensionEst3yr: number
}

/**
 * Extension premium over straight arb-path cost.
 * Pre-arb agents demand a buyout for years they'd otherwise win at arbitration;
 * the premium shrinks as remaining control shrinks and arb hearings approach.
 */
const EXTENSION_PREMIUM: Record<ArbClass, number> = {
  'pre-arb': 1.65,
  arb1: 1.42,
  arb2: 1.22,
  arb3: 1.08,
  fa: 1.00,
}

/** Infer player type from position abbreviation. */
export function inferPlayerType(positionAbbr: string | null | undefined): PlayerType {
  if (!positionAbbr) return 'batter'
  const p = positionAbbr.toUpperCase()
  if (p === 'SP' || p === 'P') return 'starter'
  if (p === 'RP') return 'reliever'
  return 'batter'
}

/** Parse Spotrac contract_status → arb class. */
export function parseArbClass(status: string | null | undefined): ArbClass {
  if (!status) return 'fa'
  const s = status.toLowerCase()
  if (s.includes('pre-arbitration') || s.includes('pre arb')) return 'pre-arb'
  if (s.includes('arbitration 1')) return 'arb1'
  if (s.includes('arbitration 2')) return 'arb2'
  if (s.includes('arbitration 3') || s.includes('arbitration 4')) return 'arb3'
  return 'fa'
}

/** Numeric rank: pre-arb=0, arb1=1, arb2=2, arb3=3, fa=4 */
function arbRank(cls: ArbClass): number {
  return { 'pre-arb': 0, arb1: 1, arb2: 2, arb3: 3, fa: 4 }[cls]
}

/** Advance arb class by one season. */
function nextClass(cls: ArbClass): ArbClass {
  const seq: ArbClass[] = ['pre-arb', 'arb1', 'arb2', 'arb3', 'fa']
  const i = seq.indexOf(cls)
  return seq[Math.min(i + 1, seq.length - 1)]
}

/** Project a salary for a given arb class, WAR, player type, and position. */
function projectSalary(
  cls: ArbClass,
  war: number,
  playerType: PlayerType,
  positionAbbr: string | null | undefined,
  knownCapHit?: number | null,
): number {
  const rate = MARKET_RATE[playerType]
  const posPremium = POSITION_PREMIUM[positionAbbr?.toUpperCase() ?? ''] ?? 1.0
  const openMarket = Math.max(MLB_MIN, war * rate * posPremium)

  if (cls === 'pre-arb') return MLB_MIN
  if (cls === 'arb1') return Math.max(MLB_MIN, openMarket * ARB_MULTIPLIERS[1])
  if (cls === 'arb2') return Math.max(MLB_MIN, openMarket * ARB_MULTIPLIERS[2])
  if (cls === 'arb3') return Math.max(MLB_MIN, openMarket * ARB_MULTIPLIERS[3])
  return knownCapHit ?? openMarket
}

/**
 * Compute 3-year arb salary forecast for a player.
 *
 * @param contractStatus  Spotrac contract_status string
 * @param lastWar         Most recent season WAR
 * @param capHit          Known cap hit (used for FA/vet players)
 * @param positionAbbr    Position abbreviation (SS, CF, SP, RP, etc.)
 */
export function forecastArb(
  contractStatus: string | null | undefined,
  lastWar: number | null | undefined,
  capHit?: number | null,
  positionAbbr?: string | null,
): ArbForecast {
  const war = Math.max(0, lastWar ?? 0.5)
  const currentClass = parseArbClass(contractStatus)
  const playerType = inferPlayerType(positionAbbr)
  const rank = arbRank(currentClass)
  const yearsControlled = Math.max(0, 4 - rank)

  const cls1 = nextClass(currentClass)
  const cls2 = nextClass(cls1)
  const cls3 = nextClass(cls2)

  const yr1 = projectSalary(cls1, war, playerType, positionAbbr, capHit)
  const yr2 = projectSalary(cls2, war, playerType, positionAbbr, capHit)
  const yr3 = projectSalary(cls3, war, playerType, positionAbbr, capHit)

  // Uncertainty bands — widen for pre-arb (fewer comps), narrow as service time accrues
  const u1 = ARB_UNCERTAINTY[cls1] ?? 0.15
  const u2 = ARB_UNCERTAINTY[cls2] ?? 0.15
  const u3 = ARB_UNCERTAINTY[cls3] ?? 0.15

  const totalCost3yr = yr1 + yr2 + yr3
  return {
    currentClass,
    playerType,
    projections: [yr1, yr2, yr3],
    projectionsLo: [yr1 * (1 - u1), yr2 * (1 - u2), yr3 * (1 - u3)],
    projectionsHi: [yr1 * (1 + u1), yr2 * (1 + u2), yr3 * (1 + u3)],
    yearsControlled,
    totalCost3yr,
    extensionEst3yr: totalCost3yr * EXTENSION_PREMIUM[currentClass],
  }
}

/** True if a player is pre-FA cost-controlled (worth showing arb ramp). */
export function isControlled(cls: ArbClass): boolean {
  return cls !== 'fa'
}
