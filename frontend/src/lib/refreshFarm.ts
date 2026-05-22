import type { FarmLevel, FarmPlayer, FarmTeam } from '../data/farm'
import { farmTeams, LEVEL_ORDER } from '../data/farm'

const MLB_BASE = 'https://statsapi.mlb.com/api/v1'

type AffiliateMeta = {
  parent_bref: string
  level: FarmLevel
  team_name: string
  team_abbrev: string | null
}

// bref ↔ parent MLB team_id (mirrors lib/format.ts on the frontend + export_farm.py)
const MLB_BY_BREF: Record<string, number> = {
  ARI: 109, ATL: 144, BAL: 110, BOS: 111, CHC: 112, CHW: 145, CIN: 113,
  CLE: 114, COL: 115, DET: 116, HOU: 117, KCR: 118, LAA: 108, LAD: 119,
  MIA: 146, MIL: 158, MIN: 142, NYM: 121, NYY: 147, OAK: 133, PHI: 143,
  PIT: 134, SDP: 135, SEA: 136, SFG: 137, STL: 138, TBR: 139, TEX: 140,
  TOR: 141, WSN: 120,
}
const BREF_BY_MLB_ID: Record<number, string> = Object.fromEntries(Object.entries(MLB_BY_BREF).map(([k, v]) => [v, k]))
const LEVEL_BY_SPORT: Record<number, FarmLevel> = { 11: 'AAA', 12: 'AA', 13: 'A+', 14: 'A', 16: 'R' }

export type FarmRefreshProgress = {
  phase: 'idle' | 'affiliates' | 'current-team' | 'rebucketing' | 'done' | 'error'
  chunksDone: number
  chunksTotal: number
  playersDone: number
  playersTotal: number
  moved: number
  error?: string
}

async function fetchJson<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { Accept: 'application/json' } })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  return r.json() as Promise<T>
}

function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = []
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size))
  return out
}

async function fetchAffiliateMap(season: number): Promise<Map<number, AffiliateMeta>> {
  const data = await fetchJson<{ teams: Array<{ id: number; name: string; abbreviation?: string; sport?: { id?: number }; parentOrgId?: number }> }>(
    `${MLB_BASE}/teams?sportIds=11,12,13,14,16&season=${season}`,
  )
  const out = new Map<number, AffiliateMeta>()
  for (const t of data.teams ?? []) {
    const parentBref = t.parentOrgId != null ? BREF_BY_MLB_ID[t.parentOrgId] : undefined
    const level = t.sport?.id != null ? LEVEL_BY_SPORT[t.sport.id] : undefined
    if (!parentBref || !level) continue
    out.set(t.id, { parent_bref: parentBref, level, team_name: t.name, team_abbrev: t.abbreviation ?? null })
  }
  return out
}

async function fetchCurrentTeamChunk(ids: number[]): Promise<Map<number, { teamId: number; teamName: string; parentOrgId: number | null; fullName: string }>> {
  const data = await fetchJson<{ people: Array<{ id: number; fullName: string; currentTeam?: { id?: number; name?: string; parentOrgId?: number } }> }>(
    `${MLB_BASE}/people?personIds=${ids.join(',')}&hydrate=currentTeam`,
  )
  const out = new Map<number, { teamId: number; teamName: string; parentOrgId: number | null; fullName: string }>()
  for (const p of data.people ?? []) {
    const ct = p.currentTeam
    if (!ct?.id) continue
    out.set(p.id, {
      teamId: ct.id,
      teamName: ct.name ?? '',
      parentOrgId: ct.parentOrgId ?? null,
      fullName: p.fullName,
    })
  }
  return out
}

/**
 * Re-bucket every farm player by their live current parent org.
 *
 * Mirrors the logic in `scripts/export_farm.py` so the browser-side refresh
 * produces an identical shape to the build-time seed — but uses live API data
 * captured at click-time. Stats remain the 2024 MiLB aggregate (DuckDB-only);
 * those are refreshed via the terminal sync command.
 */
export async function refreshFarmLive(season: number, onProgress?: (p: FarmRefreshProgress) => void): Promise<{ teams: Record<string, FarmTeam>; moved: number; unmatched: number }> {
  onProgress?.({ phase: 'affiliates', chunksDone: 0, chunksTotal: 0, playersDone: 0, playersTotal: 0, moved: 0 })

  const liveAffiliates = await fetchAffiliateMap(season)
  // Index every farm player from the seed (their 2024 stats stay; only the placement is recomputed)
  const allPlayers: Array<{ original: FarmPlayer; seedParent: string }> = []
  for (const [bref, team] of Object.entries(farmTeams)) {
    for (const lv of LEVEL_ORDER) {
      for (const p of team.levels[lv] ?? []) {
        allPlayers.push({ original: p, seedParent: bref })
      }
    }
    // Also include MLB-bucket players (they may have been demoted back to MiLB)
    for (const p of team.levels.MLB ?? []) {
      allPlayers.push({ original: p, seedParent: bref })
    }
  }
  const ids = [...new Set(allPlayers.map((x) => x.original.mlb_player_id))]
  const chunks = chunk(ids, 50)
  const totalChunks = chunks.length
  let chunksDone = 0
  let playersDone = 0

  // Fetch currentTeam in parallel (limit concurrency to avoid being rate-limited)
  const currentByPlayer = new Map<number, { teamId: number; teamName: string; parentOrgId: number | null; fullName: string }>()
  const CONCURRENCY = 6
  for (let i = 0; i < chunks.length; i += CONCURRENCY) {
    const batch = chunks.slice(i, i + CONCURRENCY)
    const results = await Promise.allSettled(batch.map((c) => fetchCurrentTeamChunk(c)))
    for (let bi = 0; bi < results.length; bi++) {
      const r = results[bi]
      if (r.status === 'fulfilled') {
        for (const [k, v] of r.value) currentByPlayer.set(k, v)
        playersDone += batch[bi].length
      }
      chunksDone += 1
    }
    onProgress?.({ phase: 'current-team', chunksDone, chunksTotal: totalChunks, playersDone, playersTotal: ids.length, moved: 0 })
  }

  // Re-bucket
  onProgress?.({ phase: 'rebucketing', chunksDone, chunksTotal: totalChunks, playersDone, playersTotal: ids.length, moved: 0 })

  const fresh: Record<string, FarmTeam> = {}
  for (const bref of Object.keys(farmTeams)) {
    fresh[bref] = { bref, season, total_players: 0, levels: { MLB: [], AAA: [], AA: [], 'A+': [], A: [], R: [] } }
  }
  let moved = 0
  let unmatched = 0

  for (const { original, seedParent } of allPlayers) {
    const ct = currentByPlayer.get(original.mlb_player_id)
    let currentParent: string | undefined
    let currentLevel: FarmLevel | undefined
    let currentTeamName = original.team_name
    let currentTeamAbbrev = original.team_abbrev

    if (ct?.teamId != null) {
      // MLB 40-man?
      if (BREF_BY_MLB_ID[ct.teamId]) {
        currentParent = BREF_BY_MLB_ID[ct.teamId]
        currentLevel = 'MLB'
        currentTeamName = ct.teamName
        currentTeamAbbrev = null
      } else {
        const meta = liveAffiliates.get(ct.teamId)
        if (meta) {
          currentParent = meta.parent_bref
          currentLevel = meta.level
          currentTeamName = meta.team_name
          currentTeamAbbrev = meta.team_abbrev
        } else if (ct.parentOrgId != null && BREF_BY_MLB_ID[ct.parentOrgId]) {
          currentParent = BREF_BY_MLB_ID[ct.parentOrgId]
          currentLevel = '?' as FarmLevel
        }
      }
    }

    if (!currentParent || !currentLevel) {
      unmatched += 1
      continue
    }

    const wasMoved = original.former_parent ? original.former_parent !== currentParent : seedParent !== currentParent
    if (wasMoved) moved += 1

    const updated: FarmPlayer = {
      ...original,
      team_id: ct?.teamId ?? original.team_id,
      team_name: currentTeamName,
      team_abbrev: currentTeamAbbrev,
      level: currentLevel,
      // Preserve the historical 2024 parent for "moved from" badges; if seed already
      // had a former_parent, keep that (deeper history). Otherwise, mark seedParent as former.
      former_team_name: original.former_team_name ?? original.team_name,
      former_parent: original.former_parent ?? (seedParent !== currentParent ? seedParent : null),
      moved_since_2024: wasMoved || original.moved_since_2024,
    }

    if (!fresh[currentParent].levels[currentLevel]) {
      // 'level' was widened above; defensively initialize
      ;(fresh[currentParent].levels as Record<string, FarmPlayer[]>)[currentLevel] = []
    }
    fresh[currentParent].levels[currentLevel].push(updated)
  }

  // Totals + sort each level (hitters by OPS desc, pitchers by ERA asc)
  for (const team of Object.values(fresh)) {
    let total = 0
    for (const lv of Object.keys(team.levels) as FarmLevel[]) {
      const arr = team.levels[lv]
      if (!arr) continue
      const hitters = arr.filter((p) => !p.is_pitcher).sort((a, b) => (b.ops_pa_weighted ?? 0) - (a.ops_pa_weighted ?? 0))
      const pitchers = arr.filter((p) => p.is_pitcher).sort((a, b) => (a.era_ip_weighted ?? 99) - (b.era_ip_weighted ?? 99))
      team.levels[lv] = [...hitters, ...pitchers]
      total += team.levels[lv].length
    }
    team.total_players = total
  }

  onProgress?.({ phase: 'done', chunksDone, chunksTotal: totalChunks, playersDone, playersTotal: ids.length, moved })
  return { teams: fresh, moved, unmatched }
}
