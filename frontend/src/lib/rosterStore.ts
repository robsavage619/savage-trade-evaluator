import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { CurrentRoster, CurrentTeam } from '../data/players'
import { roster as seed } from '../data/players'

type RosterState = {
  /** Live roster, populated when refreshed in-app. null = use build-time seed. */
  live: CurrentRoster | null
  setLive: (r: CurrentRoster) => void
  clearLive: () => void
}

export const useRosterStore = create<RosterState>()(
  persist(
    (set) => ({
      live: null,
      setLive: (live) => set({ live }),
      clearLive: () => set({ live: null }),
    }),
    { name: 'ste-roster-v1' },
  ),
)

export function useRoster(): CurrentRoster {
  const live = useRosterStore((s) => s.live)
  return live ?? seed
}

export function useTeamsByBref(): Record<string, CurrentTeam> {
  const r = useRoster()
  return Object.fromEntries(r.teams.map((t) => [t.bref, t]))
}
