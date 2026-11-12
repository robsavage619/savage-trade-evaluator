// Structural captured-WAR forecast, evaluated in the browser from parameters
// exported by scripts/export_structural.py. This file only does arithmetic on
// those numbers: the model is fit in Python (modeling/structural.py) and
// frontend/scripts/check-structural.mjs proves the two agree on golden cases.
// No imports on purpose, so Node can run this file directly.

export type StructuralParams = {
  features: string[]
  x_mean: number[]
  x_scale: number[]
  reg_coef: number[]
  reg_intercept: number
  clf_coef: number[]
  clf_intercept: number
  resid_slope: number
  resid_intercept: number
  resid_floor: number
  z_q: number[]
}

/** [held_ctrl_war, held_post_war, n_no_mlb, rate] for one player. */
export type PlayerFeat = readonly [number, number, number, number]

/** A distribution as weighted point masses. */
export type Atoms = { values: number[]; weights: number[] }

export type Summary = { mean: number; median: number; p5: number; p95: number; pPositive: number }

/** Forecast distribution of captured WAR (T through T+5) for a package of players. */
export function sideAtoms(params: StructuralParams, players: readonly PlayerFeat[]): Atoms {
  const summed: Record<string, number> = {
    held_ctrl_war: players.reduce((a, p) => a + p[0], 0),
    held_post_war: players.reduce((a, p) => a + p[1], 0),
    n_legs: players.length,
    n_no_mlb: players.reduce((a, p) => a + p[2], 0),
  }
  const xs = params.features.map((f, i) => (summed[f] - params.x_mean[i]) / params.x_scale[i])
  const dot = (coef: number[]) => coef.reduce((a, c, i) => a + c * xs[i], 0)
  const pNonzero = 1 / (1 + Math.exp(-(params.clf_intercept + dot(params.clf_coef))))
  const mu = params.reg_intercept + dot(params.reg_coef)
  const scale = Math.max(params.resid_intercept + params.resid_slope * Math.abs(mu), params.resid_floor)
  const n = params.z_q.length
  return {
    values: [0, ...params.z_q.map(z => mu + scale * z)],
    weights: [1 - pNonzero, ...params.z_q.map(() => pNonzero / n)],
  }
}

/** Distribution of A minus B for independent A and B. */
export function differenceAtoms(a: Atoms, b: Atoms): Atoms {
  const values: number[] = []
  const weights: number[] = []
  for (let i = 0; i < a.values.length; i++) {
    for (let j = 0; j < b.values.length; j++) {
      values.push(a.values[i] - b.values[j])
      weights.push(a.weights[i] * b.weights[j])
    }
  }
  return { values, weights }
}

export function summarize({ values, weights }: Atoms): Summary {
  const order = values.map((_, i) => i).sort((i, j) => values[i] - values[j])
  const quantile = (q: number) => {
    let cum = 0
    for (const k of order) {
      cum += weights[k]
      if (cum >= q - 1e-12) return values[k]
    }
    return values[order[order.length - 1]]
  }
  let mean = 0
  let pPositive = 0
  for (let i = 0; i < values.length; i++) {
    mean += values[i] * weights[i]
    if (values[i] > 0) pPositive += weights[i]
  }
  return { mean, median: quantile(0.5), p5: quantile(0.05), p95: quantile(0.95), pPositive }
}
