/**
 * Arbitration salary forecasting.
 *
 * Uses empirical multipliers derived from historical MLB arb settlements:
 *   Pre-Arb  → MLB minimum
 *   Arb 1    → ~40% of open-market value
 *   Arb 2    → ~60% of open-market value
 *   Arb 3    → ~80% of open-market value
 *   FA / Vet → open-market (or cap_hit if known)
 *
 * "Open market value" = last_war * MARKET_RATE_PER_WAR, floored at MLB minimum.
 * MARKET_RATE reflects 2025-26 $/WAR (~$8.5M, growing ~7%/yr).
 */

/** Current MLB minimum salary (2026 season). */
const MLB_MIN = 740_000

/** Open-market $/WAR for 2025-26 free agency (in dollars). */
const MARKET_RATE_PER_WAR = 8_500_000

/** Fraction of open-market value paid per arb year. */
const ARB_MULTIPLIERS: Record<number, number> = {
  1: 0.40,
  2: 0.60,
  3: 0.80,
}

export type ArbClass = 'pre-arb' | 'arb1' | 'arb2' | 'arb3' | 'fa'

export type ArbForecast = {
  currentClass: ArbClass
  /** Projected salaries for the next 3 seasons (index 0 = next season). */
  projections: [number, number, number]
  /** Seasons of team control remaining (0 = FA now, 1 = last arb year, etc.). */
  yearsControlled: number
  /** Three-season total projected cost. */
  totalCost3yr: number
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

/** Project a salary for a given arb class and estimated WAR. */
function projectSalary(cls: ArbClass, war: number, knownCapHit?: number | null): number {
  const openMarket = Math.max(MLB_MIN, war * MARKET_RATE_PER_WAR)
  if (cls === 'pre-arb') return MLB_MIN
  if (cls === 'arb1') return Math.max(MLB_MIN, openMarket * ARB_MULTIPLIERS[1])
  if (cls === 'arb2') return Math.max(MLB_MIN, openMarket * ARB_MULTIPLIERS[2])
  if (cls === 'arb3') return Math.max(MLB_MIN, openMarket * ARB_MULTIPLIERS[3])
  // FA / Vet — use known cap hit if available, else open market
  return knownCapHit ?? openMarket
}

/**
 * Compute 3-year arb salary forecast for a player.
 *
 * @param contractStatus  Spotrac contract_status string
 * @param lastWar         Most recent season WAR (used as a stable anchor)
 * @param capHit          Known cap hit (used for FA/vet players)
 */
export function forecastArb(
  contractStatus: string | null | undefined,
  lastWar: number | null | undefined,
  capHit?: number | null,
): ArbForecast {
  const war = Math.max(0, lastWar ?? 0.5)
  const currentClass = parseArbClass(contractStatus)
  const rank = arbRank(currentClass)

  // Years of team control remaining: FA = 0, arb3 = 1, arb2 = 2, arb1 = 3, pre-arb ≈ 4
  const yearsControlled = Math.max(0, 4 - rank)

  // Project the class the player will be in for each of the next 3 seasons
  const cls1 = nextClass(currentClass)
  const cls2 = nextClass(cls1)
  const cls3 = nextClass(cls2)

  const yr1 = projectSalary(cls1, war, capHit)
  const yr2 = projectSalary(cls2, war, capHit)
  const yr3 = projectSalary(cls3, war, capHit)

  return {
    currentClass,
    projections: [yr1, yr2, yr3],
    yearsControlled,
    totalCost3yr: yr1 + yr2 + yr3,
  }
}

/** True if a player is pre-FA cost-controlled (worth showing arb ramp). */
export function isControlled(cls: ArbClass): boolean {
  return cls !== 'fa'
}
