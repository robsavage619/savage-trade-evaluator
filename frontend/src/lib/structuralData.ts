import modelJson from '../data/model/structural_model.json'
import validationJson from '../data/model/structural_validation.json'
import {
  differenceAtoms,
  sideAtoms,
  summarize,
  type Atoms,
  type PlayerFeat,
  type StructuralParams,
  type Summary,
} from './structural'

const model = modelJson as unknown as {
  as_of: string
  note: string
  params: StructuralParams
  players: Record<string, PlayerFeat>
}

/** Holdout facts written by scripts/benchmark_vs_naive.py. */
export const validation = validationJson

/** Date the forecasts are priced as of, plus any note about partial-season data. */
export const structuralAsOf = { date: model.as_of, note: model.note }

const NOTHING: Atoms = { values: [0], weights: [1] }

export type SideForecast = Summary & {
  /** Sum of the players' recent WAR per season (3-2-1 weighted), for win impact. */
  ratePerSeason: number
  /** Players with no entry in the export, left out of the forecast. */
  missing: number
}

export type PackageComparison = {
  received: SideForecast
  sent: SideForecast
  /** Received minus sent, treating the two sides as independent. */
  net: Summary
  netAtoms: Atoms
}

function side(ids: readonly number[]): { forecast: SideForecast; atoms: Atoms } {
  const feats = ids.map(id => model.players[String(id)]).filter((f): f is PlayerFeat => f != null)
  const atoms = feats.length ? sideAtoms(model.params, feats) : NOTHING
  return {
    atoms,
    forecast: {
      ...summarize(atoms),
      ratePerSeason: feats.reduce((a, f) => a + f[3], 0),
      missing: ids.length - feats.length,
    },
  }
}

/** Captured-WAR forecast (T through T+5) for what a club receives and what it sends. */
export function comparePackages(
  receivedIds: readonly number[],
  sentIds: readonly number[],
): PackageComparison {
  const received = side(receivedIds)
  const sent = side(sentIds)
  const netAtoms = differenceAtoms(received.atoms, sent.atoms)
  return { received: received.forecast, sent: sent.forecast, net: summarize(netAtoms), netAtoms }
}

export type Lean = 'receive' | 'even' | 'send'

/** One rule for how far the forecast has to tilt before the UI says it leans. */
export function leanOf(net: Summary): Lean {
  if (net.mean > 0 && net.pPositive >= 0.6) return 'receive'
  if (net.mean < 0 && net.pPositive <= 0.4) return 'send'
  return 'even'
}

export const LEAN_LABEL: Record<Lean, string> = {
  receive: 'Forecast leans toward what you receive',
  even: 'Forecast is close to even',
  send: 'Forecast leans toward what you send',
}

export const fmtWar = (v: number) => `${v >= 0 ? '+' : '\u2212'}${Math.abs(v).toFixed(1)}`

const pct = (v: number) => Math.round(v * 100)

/** Holdout facts, formatted once so every surface says the same thing. */
export const validationFacts = {
  holdout: validation.holdout,
  nSides: validation.n_sides,
  coverage: (validation.coverage_90 * 100).toFixed(1),
  crpsGain: pct(1 - validation.crps / validation.crps_climatology),
  favouredWin: pct(validation.favoured_side_win_rate),
  favouredHalf: pct(validation.favoured_side_half_width),
  favouredTrades: validation.favoured_side_trades,
}
