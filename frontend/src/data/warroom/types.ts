// Types mirror the JSON contract emitted by scripts/export_warroom.py.
// buyLow and lenses remain empty slots. scenarios is now model-backed (--with-scenarios).

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

export type AttributionItem = {
  feature: string
  contribution: number
  observed: boolean
}

export type OutcomeCard = {
  mean: number | null
  p5: number | null
  p95: number | null
  pPositive: number | null
  coverageGrade: 'A' | 'B' | 'C' | 'D' | null
  observedFraction: number | null
}

export type ScenarioCard = {
  tradeEventId: number
  tradeSeason: number
  receiverBref: string
  modelVersion: string
  trainEndSeason: number
  warDelta: OutcomeCard & { attribution: AttributionItem[] }
  dollarSurplus: OutcomeCard
  surplusWins: OutcomeCard
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
  scenarios: ScenarioCard[]
  lenses: unknown[]
}
