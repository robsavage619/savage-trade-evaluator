import type { CurrentPlayer, CurrentRoster, CurrentTeam } from '../data/players'
import { roster as seed } from '../data/players'

const MLB_BASE = 'https://statsapi.mlb.com/api/v1'

type ApiRosterEntry = {
  person: { id: number; fullName: string }
  jerseyNumber?: string
  position?: { code?: string; abbreviation?: string; name?: string }
  status?: { code?: string; description?: string }
  note?: string
}

type ApiPerson = {
  id: number
  fullName?: string
  birthDate?: string
  currentAge?: number
  birthCountry?: string
  height?: string
  weight?: number
  batSide?: { code?: string }
  pitchHand?: { code?: string }
  mlbDebutDate?: string
}

export type RefreshProgress = {
  phase: 'idle' | 'rosters' | 'people' | 'merging' | 'done' | 'error'
  teamsDone: number
  teamsTotal: number
  playersDone: number
  playersTotal: number
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

/** Refresh all 30 club rosters in parallel. WAR + salary are preserved from
 *  the build-time seed (the browser can't join DuckDB); bio + roster status
 *  come live from the API. */
export async function refreshRostersLive(onProgress?: (p: RefreshProgress) => void): Promise<CurrentRoster> {
  const teams = seed.teams.map((t) => ({ bref: t.bref, mlb_team_id: t.mlb_team_id, name: t.name }))
  const totalTeams = teams.length
  let teamsDone = 0
  onProgress?.({ phase: 'rosters', teamsDone: 0, teamsTotal: totalTeams, playersDone: 0, playersTotal: 0 })

  // Fetch all rosters in parallel (with mild concurrency cap)
  const rosterByBref = new Map<string, ApiRosterEntry[]>()
  const groups = chunk(teams, 10)
  for (const group of groups) {
    await Promise.all(
      group.map(async (t) => {
        try {
          const data = await fetchJson<{ roster: ApiRosterEntry[] }>(
            `${MLB_BASE}/teams/${t.mlb_team_id}/roster?rosterType=40Man`,
          )
          rosterByBref.set(t.bref, data.roster ?? [])
        } catch (e) {
          console.warn(`roster fetch failed for ${t.bref}`, e)
          rosterByBref.set(t.bref, [])
        }
        teamsDone += 1
        onProgress?.({ phase: 'rosters', teamsDone, teamsTotal: totalTeams, playersDone: 0, playersTotal: 0 })
      }),
    )
  }

  // Collect player IDs
  const allIds = new Set<number>()
  for (const list of rosterByBref.values()) {
    for (const e of list) {
      if (e.person?.id) allIds.add(e.person.id)
    }
  }
  const ids = [...allIds]
  const totalPlayers = ids.length
  onProgress?.({ phase: 'people', teamsDone, teamsTotal: totalTeams, playersDone: 0, playersTotal: totalPlayers })

  // Bulk fetch bio data in chunks of 50
  const peopleById = new Map<number, ApiPerson>()
  const chunks = chunk(ids, 50)
  let playersDone = 0
  for (const c of chunks) {
    try {
      const data = await fetchJson<{ people: ApiPerson[] }>(`${MLB_BASE}/people?personIds=${c.join(',')}`)
      for (const p of data.people ?? []) peopleById.set(p.id, p)
    } catch (e) {
      console.warn('person fetch chunk failed', e)
    }
    playersDone += c.length
    onProgress?.({ phase: 'people', teamsDone, teamsTotal: totalTeams, playersDone, playersTotal: totalPlayers })
  }

  // Build lookup from existing seed for WAR / salary preservation
  onProgress?.({ phase: 'merging', teamsDone, teamsTotal: totalTeams, playersDone, playersTotal: totalPlayers })
  const seedById = new Map<number, CurrentPlayer>()
  for (const t of seed.teams) for (const p of t.players) seedById.set(p.mlb_player_id, p)

  const today = new Date()
  const teamsOut: CurrentTeam[] = teams.map(({ bref, mlb_team_id, name }) => {
    const list = rosterByBref.get(bref) ?? []
    const players: CurrentPlayer[] = list
      .map((e) => {
        const pid = e.person?.id
        if (!pid) return null
        const bio = peopleById.get(pid)
        const existing = seedById.get(pid)
        return {
          mlb_player_id: pid,
          name: e.person.fullName,
          jersey: e.jerseyNumber ?? null,
          position_code: e.position?.code ?? null,
          position_abbr: e.position?.abbreviation ?? null,
          position_name: e.position?.name ?? null,
          status_code: e.status?.code ?? null,
          status_desc: e.status?.description ?? null,
          note: e.note ?? null,
          birth_date: bio?.birthDate ?? existing?.birth_date ?? null,
          age: bio?.currentAge ?? existing?.age ?? null,
          birth_country: bio?.birthCountry ?? existing?.birth_country ?? null,
          height: bio?.height ?? existing?.height ?? null,
          weight: bio?.weight ?? existing?.weight ?? null,
          bat_side: bio?.batSide?.code ?? existing?.bat_side ?? null,
          pitch_hand: bio?.pitchHand?.code ?? existing?.pitch_hand ?? null,
          mlb_debut_date: bio?.mlbDebutDate ?? existing?.mlb_debut_date ?? null,
          last_year: existing?.last_year ?? null,
          last_war: existing?.last_war ?? null,
          last_salary: existing?.last_salary ?? null,
          // Preserve Spotrac contract overlay + awards from the build-time seed
          spotrac_season: existing?.spotrac_season ?? null,
          contract_status: existing?.contract_status ?? null,
          service_time: existing?.service_time ?? null,
          acquired_method: existing?.acquired_method ?? null,
          cap_hit: existing?.cap_hit ?? null,
          base_salary_spotrac: existing?.base_salary_spotrac ?? null,
          awards: existing?.awards ?? null,
        } satisfies CurrentPlayer
      })
      .filter((p): p is CurrentPlayer => p !== null)
    return { bref, mlb_team_id, name, roster_count: players.length, players }
  })

  const out: CurrentRoster = {
    refreshed_at: today.toISOString(),
    season_used_for_war: seed.season_used_for_war,
    team_count: teamsOut.length,
    player_count: teamsOut.reduce((a, t) => a + t.roster_count, 0),
    teams: teamsOut,
  }
  onProgress?.({ phase: 'done', teamsDone, teamsTotal: totalTeams, playersDone, playersTotal: totalPlayers })
  return out
}
