import indexJson from '../data/warroom/index.json'
import type { TeamPayload, WarRoomIndex } from '../data/warroom/types'

export const warRoomIndex = indexJson as WarRoomIndex

// Lazily resolve per-club payloads without bundling all 30 eagerly.
const teamLoaders = import.meta.glob<{ default: TeamPayload }>('../data/warroom/*.json')

export async function loadTeamPayload(bref: string): Promise<TeamPayload | null> {
  const loader = teamLoaders[`../data/warroom/${bref}.json`]
  if (!loader) return null
  const mod = await loader()
  return mod.default
}
