/**
 * Deals that clear — cross-team hole/surplus overlap engine.
 *
 * Algorithm:
 *  For each partner team P ≠ you:
 *    theirFills  = intersect(P.surpluses, your.holes)       — what they can give you
 *    yourFills   = intersect(your.surpluses, P.holes)       — what you can give them
 *    score       = Σ(theirFills hole severity) × Σ(yourFills hole severity)
 *                  × payroll_compat × posture_bonus
 *
 * Only teams with score > 0 on BOTH sides are surfaced (true mutual deals).
 */

import { warRoomIndex } from './warroomData'
import type { HoleEntry, TeamPayload } from '../data/warroom/types'

const SEVERITY_WEIGHT = { critical: 3, warning: 1.5, ok: 0.5 }

export type DealCandidate = {
  partnerBref: string
  partnerName: string
  partnerPosture: 'buy' | 'hold' | 'sell'
  partnerWL: string
  partnerHeadroom: number
  score: number
  /** Your holes this partner can fill (they have surplus here) */
  theyFill: HoleEntry[]
  /** Their holes you can fill (you have surplus here) */
  youFill: HoleEntry[]
}

function positionMatch(holes: HoleEntry[], surpluses: HoleEntry[]): HoleEntry[] {
  const surplusPositions = new Set(surpluses.map(s => s.position))
  return holes.filter(h => surplusPositions.has(h.position))
}

function severityScore(entries: HoleEntry[]): number {
  return entries.reduce((acc, h) => acc + (SEVERITY_WEIGHT[h.severity] ?? 0.5), 0)
}

export function computeDeals(
  yourBref: string,
  yourPayload: TeamPayload,
  allPayloads: Record<string, TeamPayload>,
): DealCandidate[] {
  const yourIdx = warRoomIndex.teams.find(t => t.code === yourBref)
  if (!yourIdx) return []

  const results: DealCandidate[] = []

  for (const [bref, payload] of Object.entries(allPayloads)) {
    if (bref === yourBref) continue
    const partnerIdx = warRoomIndex.teams.find(t => t.code === bref)
    if (!partnerIdx) continue

    // Same-posture deals (buy↔buy, sell↔sell) happen constantly at the deadline —
    // contenders swap positional fits, rebuilders exchange veterans. Do not exclude them;
    // apply a modest score discount to rank them below the cleaner cross-posture pairings.

    const theyFill = positionMatch(yourPayload.holes, payload.surpluses)
    const youFill = positionMatch(payload.holes, yourPayload.surpluses)

    // Both sides must get something
    if (theyFill.length === 0 || youFill.length === 0) continue

    const theirSide = severityScore(theyFill)
    const yourSide = severityScore(youFill)

    // Payroll compat: penalize if partner is over CBT and can't absorb salary
    const payrollBonus = partnerIdx.payrollHeadroom > 20_000_000 ? 1.2
      : partnerIdx.payrollHeadroom > 0 ? 1.0
      : 0.6  // over CBT — can still deal but harder

    // Posture bonus: buy↔sell is the cleanest pairing and gets a premium.
    // Same-posture gets a mild discount (still very real, just harder to close).
    // hold↔anything is neutral.
    const postureBonus =
      (yourIdx.windowPosture === 'buy' && partnerIdx.windowPosture === 'sell') ||
      (yourIdx.windowPosture === 'sell' && partnerIdx.windowPosture === 'buy') ? 1.4 :
      partnerIdx.windowPosture === yourIdx.windowPosture ? 0.85 : 1.0

    const score = theirSide * yourSide * payrollBonus * postureBonus

    results.push({
      partnerBref: bref,
      partnerName: partnerIdx.name,
      partnerPosture: partnerIdx.windowPosture,
      partnerWL: `${partnerIdx.w}–${partnerIdx.l}`,
      partnerHeadroom: partnerIdx.payrollHeadroom,
      score,
      theyFill,
      youFill,
    })
  }

  return results.sort((a, b) => b.score - a.score).slice(0, 10)
}
