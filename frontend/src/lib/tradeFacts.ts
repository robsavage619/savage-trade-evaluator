import type { CurrentPlayer } from '../data/players'
import { forecastArb, isControlled } from './arbForecast'
import { baseWar, effectivePos } from './hypothetical'

export type PackageFacts = {
  /** Projected first-year salary of the package. */
  yr1Cost: number
  /** Projected three-year cost of the players still under team control. */
  controlledCost3yr: number
  /** Realistic lock-up cost of the controlled players. */
  extensionEst: number
}

/** Salary and control facts for a set of players, straight from the contract data.
 *  They sit beside the forecast as costs; they are not part of it. */
export function packageFacts(players: readonly CurrentPlayer[]): PackageFacts {
  let yr1Cost = 0
  let controlledCost3yr = 0
  let extensionEst = 0
  for (const p of players) {
    const arb = forecastArb(p.contract_status, baseWar(p), p.cap_hit, effectivePos(p))
    yr1Cost += arb.projections[0]
    if (isControlled(arb.currentClass)) controlledCost3yr += arb.totalCost3yr
    if (arb.yearsControlled > 0) extensionEst += arb.extensionEst3yr
  }
  return { yr1Cost, controlledCost3yr, extensionEst }
}
