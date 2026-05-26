/**
 * Buy-low radar — surfaces cost-efficient players matching your positional holes.
 *
 * Ranking metric = control-window SURPLUS WAR:
 *   Σ over remaining control years of ( aging-adjusted, dev-gated WAR − cost / $WAR )
 *
 * Why not a WAR/cost ratio? For arb-projected players, projected cost scales
 * roughly linearly with WAR (cost = WAR × $/WAR × arb_multiplier), so a naive
 * ratio cancels WAR and collapses every candidate to the same number. Absolute
 * surplus WAR does not cancel — high-WAR controllable talent rises to the top,
 * which is exactly the buy-low signal we want.
 *
 * Filters:
 *  - Player's position matches one of your holes
 *  - Source team has that position as a surplus (willing to deal)
 *  - Source team's posture is 'sell' or 'hold' (not a fellow buyer)
 *  - Player has ≥1 year of control and positive projected surplus
 */

import type { CurrentPlayer, CurrentTeam } from '../data/players'
import type { HoleEntry, TeamPayload } from '../data/warroom/types'
import { warRoomIndex } from './warroomData'
import { forecastArb, isControlled } from './arbForecast'
import type { ArbForecast } from './arbForecast'
import { agingDelta, devAdjust, MARKET_RATE } from './hypothetical'

// Rough position normalisation: maps MLB position codes/abbrevs to hole position keys
const POS_MAP: Record<string, string[]> = {
  SP: ['P', 'SP'],
  RP: ['P', 'RP'],
  C: ['C'],
  '1B': ['1B'],
  '2B': ['2B'],
  SS: ['SS'],
  '3B': ['3B'],
  LF: ['LF', 'OF'],
  CF: ['CF', 'OF'],
  RF: ['RF', 'OF'],
  DH: ['DH', '1B'],
  OF: ['LF', 'CF', 'RF', 'OF'],
}

function positionMatches(playerPos: string | null, holePos: string): boolean {
  if (!playerPos) return false
  const p = playerPos.toUpperCase()
  const h = holePos.toUpperCase()
  if (p === h) return true
  const mapped = POS_MAP[h] ?? []
  return mapped.includes(p)
}

/** Control-window surplus WAR — the non-canceling buy-low signal. */
function controlWindowSurplus(player: CurrentPlayer, devMul: number, arb: ArbForecast): number {
  const baseWar = Math.max(0, player.last_war ?? 0)
  const age = player.age ?? 27
  const years = Math.min(3, Math.max(1, arb.yearsControlled))
  let war = baseWar
  let surplus = 0
  for (let t = 0; t < years; t++) {
    war = Math.max(0, war + agingDelta(age + t))
    const adjWar = devAdjust(war, age + t, devMul)
    surplus += adjWar - arb.projections[t] / MARKET_RATE
  }
  return surplus
}

export type BuyLowCandidate = {
  player: CurrentPlayer
  sourceTeam: CurrentTeam
  sourcePosture: 'buy' | 'hold' | 'sell'
  /** Which of your holes this player addresses */
  holesFilled: HoleEntry[]
  /** Control-window surplus WAR — the ranking signal (net of projected salary). */
  surplusWar: number
  /** Year-1 projected salary. */
  yr1Cost: number
  yearsControlled: number
  /** Year-1 dev-adjusted WAR projection (display). */
  adjWar: number
  /** Surplus WAR ÷ year-1 cost (in market-WAR units). Higher = more production per dollar. */
  valueScore: number
}

export function computeBuyLow(
  yourBref: string,
  yourPayload: TeamPayload,
  allTeams: CurrentTeam[],
  allPayloads: Record<string, TeamPayload>,
  devMul: number,
): BuyLowCandidate[] {
  if (yourPayload.holes.length === 0) return []

  const results: BuyLowCandidate[] = []

  for (const team of allTeams) {
    if (team.bref === yourBref) continue
    const idx = warRoomIndex.teams.find(t => t.code === team.bref)
    if (!idx) continue

    // Only source from non-buyers (sellers and hold teams are moveable)
    if (idx.windowPosture === 'buy') continue

    const partnerPayload = allPayloads[team.bref]
    if (!partnerPayload) continue

    // Their surpluses — positions they're willing to deal from
    const surplusPositions = new Set(partnerPayload.surpluses.map(s => s.position))

    for (const player of team.players) {
      // Pass position_abbr so arb pricing uses the correct player-type $/WAR + premium.
      const arb = forecastArb(player.contract_status, player.last_war, player.cap_hit, player.position_abbr)
      if (!isControlled(arb.currentClass)) continue        // FA — open market, not a buy-low
      if (arb.yearsControlled === 0) continue
      const war = player.last_war ?? 0
      if (war <= 0) continue                               // replacement or below — not worth it

      const surplusWar = controlWindowSurplus(player, devMul, arb)
      if (surplusWar < 0.3) continue                       // must be a net-positive surplus

      // Does player's position match any of our holes?
      const holesFilled = yourPayload.holes.filter(h =>
        positionMatches(player.position_abbr, h.position)
      )
      if (holesFilled.length === 0) continue

      // Does source team have surplus at this position? (willing to deal)
      const hasMatchingSurplus = holesFilled.some(h =>
        [...surplusPositions].some(sp => positionMatches(player.position_abbr, sp) || sp === h.position)
      )
      if (!hasMatchingSurplus) continue

      const age = player.age ?? 27
      const yr1War = Math.max(0, war + agingDelta(age))
      const yr1Cost = arb.projections[0]
      const costInWar = yr1Cost / MARKET_RATE
      results.push({
        player,
        sourceTeam: team,
        sourcePosture: idx.windowPosture,
        holesFilled,
        surplusWar,
        yr1Cost,
        yearsControlled: arb.yearsControlled,
        adjWar: devAdjust(yr1War, age, devMul),
        valueScore: costInWar > 0 ? surplusWar / costInWar : surplusWar,
      })
    }
  }

  // Sort by surplus WAR descending, top 12
  return results
    .sort((a, b) => b.surplusWar - a.surplusWar)
    .slice(0, 12)
}
