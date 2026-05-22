import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { FarmPlayer, FarmTeam } from '../data/farm'
import { farmTeams as seedFarm, farmSeason as seedSeason, farmGeneratedAt as seedGeneratedAt, LEVEL_ORDER } from '../data/farm'

type LiveFarmPayload = {
  refreshed_at: string
  season: number
  teams: Record<string, FarmTeam>
}

type FarmState = {
  live: LiveFarmPayload | null
  setLive: (payload: LiveFarmPayload) => void
  clearLive: () => void
}

export const useFarmStore = create<FarmState>()(
  persist(
    (set) => ({
      live: null,
      setLive: (live) => set({ live }),
      clearLive: () => set({ live: null }),
    }),
    { name: 'ste-farm-v1' },
  ),
)

export function useFarmTeams(): Record<string, FarmTeam> {
  const live = useFarmStore((s) => s.live)
  return live?.teams ?? seedFarm
}

export function useFarmMeta(): { refreshed_at: string; season: number; source: 'live' | 'seed' } {
  const live = useFarmStore((s) => s.live)
  if (live) return { refreshed_at: live.refreshed_at, season: live.season, source: 'live' }
  return { refreshed_at: seedGeneratedAt, season: seedSeason, source: 'seed' }
}

export function useFarmForOrg(bref: string): FarmTeam | undefined {
  const teams = useFarmTeams()
  return teams[bref]
}

let _farmById: Map<number, { player: FarmPlayer; parentBref: string }> | null = null
let _farmByIdSource: object | null = null

export function useFarmPlayerLookup(): Map<number, { player: FarmPlayer; parentBref: string }> {
  const teams = useFarmTeams()
  // Memoize against the source object identity — rebuilds on live updates
  if (_farmByIdSource !== teams || _farmById === null) {
    const m = new Map<number, { player: FarmPlayer; parentBref: string }>()
    for (const [bref, team] of Object.entries(teams)) {
      for (const lv of LEVEL_ORDER) {
        for (const p of team.levels[lv] ?? []) {
          if (!m.has(p.mlb_player_id)) m.set(p.mlb_player_id, { player: p, parentBref: bref })
        }
      }
      for (const p of team.levels.MLB ?? []) {
        if (!m.has(p.mlb_player_id)) m.set(p.mlb_player_id, { player: p, parentBref: bref })
      }
    }
    _farmById = m
    _farmByIdSource = teams
  }
  return _farmById
}
