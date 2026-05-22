// Types mirror the JSON contract emitted by scripts/export_warroom.py.
// Pre-model heuristic layer: scenarios/buyLow/lenses are intentionally empty slots.

export type WindowPosture = 'buy' | 'hold' | 'sell'
export type Severity = 'critical' | 'warning' | 'ok'

export type Citation = { label: string; detail: string }

export type IndexTeam = {
  code: string
  name: string
  division: string
  w: number
  l: number
  winPct: number
  gamesBack: number
  windowPosture: WindowPosture
  payrollCommitted: number
  payrollHeadroom: number
}

export type WarRoomIndex = {
  season: number
  asOfGames: number
  blendWeight: number
  cbtThreshold: number
  generatedAt: string
  teams: IndexTeam[]
}

export type HoleEntry = {
  position: string
  rosteredWar: number
  farmWar: number
  replacementBaseline: number
  holeScore: number
  severity: Severity
  surplus?: number
  citation: Citation
}

export type ExpiringContract = {
  player: string
  position: string | null
  capHit: number
  status: string | null
}

export type TeamPayload = {
  team: string
  context: {
    standingsLine: string
    windowPosture: WindowPosture
    postureRationale: string
    citation: Citation
    payroll: { committed: number; cbtThreshold: number; headroom: number }
    expiringContracts: ExpiringContract[]
    blend: { w2026: number; w2025: number; citation: Citation }
  }
  holes: HoleEntry[]
  surpluses: HoleEntry[]
  buyLow: unknown[]
  scenarios: unknown[]
  lenses: unknown[]
}
