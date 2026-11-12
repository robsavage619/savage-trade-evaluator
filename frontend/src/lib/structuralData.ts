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
  return {
    received: received.forecast,
    sent: sent.forecast,
    net: summarize(differenceAtoms(received.atoms, sent.atoms)),
  }
}
