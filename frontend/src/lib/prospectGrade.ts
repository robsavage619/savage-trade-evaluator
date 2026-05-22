import type { FarmPlayer } from '../data/farm'

/**
 * Proxy scout grade on the standard 20-80 scale. There are no real prospect
 * grades in our DB; this synthesizes one from age-vs-level + performance, the
 * three components most prospect graders weight heavily. Replace once Baseball
 * America / FanGraphs grades are ingested.
 *
 * Inputs:
 *   - level (AAA hardest, A easiest)
 *   - age relative to typical level age (lower age = bonus)
 *   - OPS (hitters) or ERA (pitchers) vs cohort-typical
 *   - top-level reached this season (reaching higher level = scarcity bonus)
 */

import type { FarmLevel } from '../data/farm'

// Typical age for a 50-grade prospect at each level (rough scout heuristic)
const TYPICAL_AGE: Record<FarmLevel, number> = {
  MLB: 27,
  AAA: 25,
  AA: 23,
  'A+': 22,
  A: 21,
  R: 19,
}

// Anchor performance for a 50-grade at each level (hitter OPS / pitcher ERA)
const HITTER_BASE_OPS: Record<FarmLevel, number> = {
  MLB: 0.74,
  AAA: 0.78,
  AA: 0.72,
  'A+': 0.7,
  A: 0.68,
  R: 0.7,
}
const PITCHER_BASE_ERA: Record<FarmLevel, number> = {
  MLB: 4.2,
  AAA: 4.4,
  AA: 4.0,
  'A+': 3.8,
  A: 3.6,
  R: 4.0,
}

const LEVEL_BONUS: Record<FarmLevel, number> = {
  MLB: 8,
  AAA: 6,
  AA: 4,
  'A+': 1,
  A: -2,
  R: -4,
}

export function scoutGrade(p: FarmPlayer): number {
  let g = 50

  // Level bonus (a 22yo in AAA outranks a 22yo in A)
  g += LEVEL_BONUS[p.level]

  // Age bonus (younger than typical = bonus, older = penalty)
  if (p.age != null) {
    const typical = TYPICAL_AGE[p.level]
    const ageDelta = typical - p.age // positive = young for level
    g += ageDelta * 2.5
  }

  // Performance vs cohort
  if (!p.is_pitcher && p.ops_pa_weighted != null && (p.pa ?? 0) >= 30) {
    const base = HITTER_BASE_OPS[p.level]
    const delta = p.ops_pa_weighted - base
    g += delta * 60 // ~+0.1 OPS = +6 grade
  } else if (p.is_pitcher && p.era_ip_weighted != null && (p.ip ?? 0) >= 15) {
    const base = PITCHER_BASE_ERA[p.level]
    const delta = base - p.era_ip_weighted // positive = better
    g += delta * 3.5 // -1 ERA below baseline = +3.5 grade
  } else {
    // Insufficient sample — anchor closer to 45 (modest below average)
    g -= 4
  }

  // Top-level scarcity: if they reached a higher level than their primary
  if (p.top_sport_id != null && p.level === 'AA' && p.top_sport_id === 11) g += 3
  if (p.top_sport_id != null && p.level === 'A+' && (p.top_sport_id === 11 || p.top_sport_id === 12)) g += 3

  // Clamp + round to nearest 5 (standard scout-grade granularity)
  const clamped = Math.max(20, Math.min(80, g))
  return Math.round(clamped / 5) * 5
}

export function gradeTone(g: number): 'pos' | 'neg' | 'neutral' {
  if (g >= 60) return 'pos'
  if (g <= 40) return 'neg'
  return 'neutral'
}

export function gradeLabel(g: number): string {
  if (g >= 70) return 'Top 100'
  if (g >= 60) return 'Org top-10'
  if (g >= 55) return 'Above avg'
  if (g >= 45) return 'Org depth'
  return 'Org filler'
}
