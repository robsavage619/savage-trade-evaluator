import type { CurrentPlayer } from '../data/players'
import { forecastArb, isControlled } from './arbForecast'
import { nextSalary } from './contractDollars'
import { baseWar, effectivePos } from './hypothetical'

export type PackageFacts = {
  /** Next-season salary of the package: Baseball-Reference where it lists a figure,
   *  else the projection. */
  yr1Cost: number
  /** Players whose figure came from Baseball-Reference. */
  listedCount: number
  /** Players priced by the projection because Baseball-Reference states no figure. */
  projectedCount: number
  /** Projected three-year cost of the players still under team control. */
  controlledCost3yr: number
  /** Realistic lock-up cost of the controlled players. */
  extensionEst: number
}

/** Salary and control facts for a set of players, straight from the contract data.
 *  They sit beside the forecast as costs; they are not part of it. */
export function packageFacts(players: readonly CurrentPlayer[]): PackageFacts {
  let yr1Cost = 0
  let listedCount = 0
  let projectedCount = 0
  let controlledCost3yr = 0
  let extensionEst = 0
  for (const p of players) {
    const arb = forecastArb(p.contract_status, baseWar(p), p.cap_hit, effectivePos(p))
    const listed = nextSalary(p.mlb_player_id)
    if (listed) {
      yr1Cost += listed.amount
      listedCount += 1
    } else {
      yr1Cost += arb.projections[0]
      projectedCount += 1
    }
    if (isControlled(arb.currentClass)) controlledCost3yr += arb.totalCost3yr
    if (arb.yearsControlled > 0) extensionEst += arb.extensionEst3yr
  }
  return { yr1Cost, listedCount, projectedCount, controlledCost3yr, extensionEst }
}

/** One line saying where a salary comparison's figures came from. */
export function salarySource(a: PackageFacts, b: PackageFacts): string {
  const listed = a.listedCount + b.listedCount
  const total = listed + a.projectedCount + b.projectedCount
  return `Baseball-Reference for ${listed} of ${total}, projected for the rest`
}
