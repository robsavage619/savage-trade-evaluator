import dollarsJson from '../data/model/contract_dollars.json'

import { MLB_MIN } from './arbForecast'

/** g guaranteed salary, o option value (exercise assumed), a arbitration estimate,
 *  p a pre-arbitration year (no figure printed, priced at the league minimum). */
export type DollarKind = 'g' | 'o' | 'a' | 'p'

const data = dollarsJson as unknown as {
  as_of: string
  season: number
  players: Record<string, [DollarKind, number]>
}

/** Season the dollars are for, and the snapshot date they come from. */
export const dollarsAsOf = { season: data.season, asOf: data.as_of }

/** Baseball-Reference's salary for the player's next season, or null when it states none
 *  (pre-arbitration, free agent, or not on a club's contracts page). */
export function nextSalary(id: number): { amount: number; kind: DollarKind } | null {
  const hit = data.players[String(id)]
  if (!hit) return null
  return { kind: hit[0], amount: hit[0] === 'p' ? MLB_MIN : hit[1] }
}
