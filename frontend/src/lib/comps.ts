import playerIndexJson from '../data/seed/player_index.json'

export type FingerprintRow = Record<string, number | null | undefined>

export type IndexedPlayer = {
  id: number
  name: string
  team: string
  pos_code: string | null
  age: number | null
  war: number | null
  salary: number | null
  pitch_hand: string | null
  bat_side: string | null
  is_pitcher: boolean
  fp: FingerprintRow | null
}

type Payload = { generated_at: string; count: number; players: IndexedPlayer[] }

const data = playerIndexJson as unknown as Payload
export const playerIndex: IndexedPlayer[] = data.players

const PITCHER_FEATURES = ['xwoba', 'xera', 'k_percent', 'bb_percent', 'whiff_percent', 'chase_percent', 'fb_velocity', 'fb_spin', 'curve_spin', 'hard_hit_percent', 'brl_percent']
const BATTER_FEATURES = ['xwoba', 'xba', 'xslg', 'k_percent', 'bb_percent', 'whiff_percent', 'chase_percent', 'exit_velocity', 'hard_hit_percent', 'brl_percent', 'sprint_speed']

function vectorize(fp: FingerprintRow | null | undefined, features: string[]): number[] {
  if (!fp) return []
  return features.map((k) => {
    const v = fp[k]
    return typeof v === 'number' && !Number.isNaN(v) ? v : 50 // neutral fallback
  })
}

function distance(a: number[], b: number[]): number {
  if (a.length !== b.length || a.length === 0) return Number.POSITIVE_INFINITY
  let sumSq = 0
  for (let i = 0; i < a.length; i++) sumSq += (a[i] - b[i]) ** 2
  return Math.sqrt(sumSq / a.length)
}

const POS_GROUP: Record<string, 'P' | 'C' | 'IF' | 'OF' | 'DH'> = {
  '1': 'P', '2': 'C',
  '3': 'IF', '4': 'IF', '5': 'IF', '6': 'IF',
  '7': 'OF', '8': 'OF', '9': 'OF', O: 'OF',
  '10': 'DH',
}

export type CompResult = {
  player: IndexedPlayer
  score: number // 0-100, higher = more similar
  fingerprintDistance: number
  ageDelta: number
  warDelta: number
}

/**
 * Find league-wide comparables to a focus player.
 * Filters: same position group, age ±3, has fingerprint coverage.
 * Score: weighted combination of fingerprint Euclidean distance + age + WAR proximity.
 */
export function findComps(focusId: number, opts?: { limit?: number; sameLeague?: boolean }): CompResult[] {
  const limit = opts?.limit ?? 8
  const focus = playerIndex.find((p) => p.id === focusId)
  if (!focus) return []

  const features = focus.is_pitcher ? PITCHER_FEATURES : BATTER_FEATURES
  const focusVec = vectorize(focus.fp, features)
  const focusGroup = POS_GROUP[focus.pos_code ?? '']

  const candidates = playerIndex.filter((p) => {
    if (p.id === focus.id) return false
    if (focus.is_pitcher !== p.is_pitcher) return false
    if (focusGroup && POS_GROUP[p.pos_code ?? ''] !== focusGroup) return false
    if (focus.age != null && p.age != null && Math.abs(p.age - focus.age) > 3) return false
    return true
  })

  const scored = candidates.map((p) => {
    const v = vectorize(p.fp, features)
    const fpDist = focusVec.length === 0 || v.length === 0 ? 999 : distance(focusVec, v)
    const ageDelta = focus.age != null && p.age != null ? Math.abs(p.age - focus.age) : 0
    const warDelta = focus.war != null && p.war != null ? Math.abs(p.war - focus.war) : 0
    // Combined cost: fingerprint dominates (max ~30 with neutralized vec), age weighted, WAR small
    const cost = fpDist * 1.0 + ageDelta * 2.5 + warDelta * 1.5
    const score = Math.max(0, Math.min(100, 100 - cost * 1.8))
    return { player: p, score, fingerprintDistance: fpDist, ageDelta, warDelta }
  })

  scored.sort((a, b) => b.score - a.score)
  return scored.slice(0, limit)
}
