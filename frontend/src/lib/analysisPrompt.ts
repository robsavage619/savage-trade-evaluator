/**
 * Bring-your-own-Claude analysis loop.
 *
 * The app cannot call an LLM directly (static frontend, no API key). Instead:
 *   1. buildAnalysisPrompt() assembles every war-room data point — including
 *      grounded two-sided package skeletons with real surplus-WAR/$ figures —
 *      into a single self-contained prompt with a strict JSON output schema.
 *   2. The user pastes it into Claude, which returns a structured GM brief.
 *   3. parseAnalysisReport() robustly extracts the JSON back into an
 *      AnalysisReport the UI renders as charts, deal sheets, and a target board.
 *
 * Design principle (from the GM panel): the deterministic math — surplus WAR,
 * arb cost, cap proration — is computed HERE and injected, so the LLM reasons
 * and synthesizes rather than inventing numbers. The LLM's job is judgment:
 * package construction, tiering, framing, the daily move, counterparty order.
 */

import type { CurrentPlayer, CurrentTeam } from '../data/players'
import type { IndexTeam, TeamPayload } from '../data/warroom/types'
import type { BuyLowCandidate } from './buyLowEngine'
import type { DealCandidate } from './dealsEngine'
import { agingDelta } from './hypothetical'
import { forecastArb, parseArbClass } from './arbForecast'
import type { ArbClass } from './arbForecast'

// ── report schema (what Claude must return) ────────────────────────────────────

export type AnalysisVerdict =
  | 'aggressive-buy' | 'selective-buy' | 'hold-and-assess' | 'soft-sell' | 'full-teardown'
export type FindingKind = 'critical' | 'opportunity' | 'watch' | 'strength'
export type Horizon = 'now' | 'deadline' | 'offseason' | 'multi-year'
export type MatrixCategory = 'acquire' | 'trade-away' | 'extend' | 'hold'
export type Materiality = 'quiet' | 'notable' | 'urgent'
export type Tier = 'primary' | 'fallback' | 'dart-throw'
export type SellerMotivation = 'forced' | 'opportunistic' | 'reluctant' | 'unknown'
export type Overpay = 'you-overpay' | 'fair' | 'you-win'
export type Posture = 'buy' | 'hold' | 'sell'

export type PackagePlayer = { player: string; position: string; war3yr: number; surplusWar: number }

export type AnalysisReport = {
  team: string
  headline: string
  verdict: AnalysisVerdict
  confidence: number
  executiveSummary: string

  todaysMove: {
    materiality: Materiality
    action: string
    target: string | null
    counterparty: string | null
    rationale: string
    ifQuiet: string
  } | null

  keyFindings: { title: string; detail: string; kind: FindingKind }[]

  recommendations: {
    rank: number
    action: string
    rationale: string
    targets: string[]
    confidence: number
    impactWar: number
    horizon: Horizon
  }[]

  proposedPackages: {
    partner: string
    partnerPosture: Posture
    youReceive: PackagePlayer[]
    youSend: PackagePlayer[]
    fillsYourHoles: string[]
    fillsTheirHoles: string[]
    netSurplusWar: number       // + = your favor, − = you overpay
    dollarsToYouM: number       // prorated salary you take on
    overpay: Overpay
    likelihood: number          // 0-100
    likelihoodDrivers: string[]
    blockers: string[]
    framing: string             // the one-line pitch to the counterparty
  }[]

  targetBoard: {
    tier: Tier
    position: string
    player: string
    fromTeam: string
    controlYears: number
    arbClass: string
    surplusWar: number
    yr1CostM: number
    sellerMotivation: SellerMotivation
    likelyAsk: string
    healthFlag: string | null
  }[]

  counterpartyLeverage: {
    team: string
    posture: Posture
    leverageShift: number       // -100..100, negative = their position weakening (your opening)
    trigger: string
    callPriority: number
    openWith: string
  }[]

  capImpact: {
    player: string
    proratedRemainingM: number
    tierAfter: 0 | 1 | 2 | 3
    trueDollarCostM: number     // prorated × (1 + marginal tax)
    note: string
  }[]

  priorityMatrix: {
    label: string; costM: number; impactWar: number; feasibility: number; category: MatrixCategory
  }[]
  riskRadar: { axis: string; score: number }[]
  winProjection: { year: number; floor: number; expected: number; ceiling: number }[]
  contentionTimeline: { year: number; competitiveness: number; note?: string }[]
  generatedAt?: string
}

const VERDICTS: AnalysisVerdict[] = ['aggressive-buy', 'selective-buy', 'hold-and-assess', 'soft-sell', 'full-teardown']
const FINDING_KINDS: FindingKind[] = ['critical', 'opportunity', 'watch', 'strength']
const HORIZONS: Horizon[] = ['now', 'deadline', 'offseason', 'multi-year']
const MATRIX_CATS: MatrixCategory[] = ['acquire', 'trade-away', 'extend', 'hold']
const MATERIALITY: Materiality[] = ['quiet', 'notable', 'urgent']
const TIERS: Tier[] = ['primary', 'fallback', 'dart-throw']
const MOTIVATIONS: SellerMotivation[] = ['forced', 'opportunistic', 'reluctant', 'unknown']
const OVERPAYS: Overpay[] = ['you-overpay', 'fair', 'you-win']
const POSTURES: Posture[] = ['buy', 'hold', 'sell']

// ── parsing ─────────────────────────────────────────────────────────────────────

function extractJsonObject(raw: string): unknown {
  let s = raw.trim()
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) s = fence[1].trim()
  const start = s.indexOf('{')
  const end = s.lastIndexOf('}')
  if (start < 0 || end < 0 || end <= start) {
    throw new Error('No JSON object found in the pasted text. Paste Claude\'s full response.')
  }
  return JSON.parse(s.slice(start, end + 1))
}

const num = (v: unknown, d = 0): number => (typeof v === 'number' && isFinite(v) ? v : d)
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
const str = (v: unknown, d = ''): string => (typeof v === 'string' ? v : d)
const strN = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v : null)
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const strArr = (v: unknown): string[] => arr(v).map(x => str(x)).filter(Boolean)
const oneOf = <T extends string>(v: unknown, allowed: T[], d: T): T =>
  (typeof v === 'string' && (allowed as string[]).includes(v) ? (v as T) : d)
const tier3 = (v: unknown): 0 | 1 | 2 | 3 => {
  const n = num(v, 0)
  return (n === 1 || n === 2 || n === 3 ? n : 0)
}

function pkgPlayers(v: unknown): PackagePlayer[] {
  return arr(v).map(p => {
    const r = p as Record<string, unknown>
    return {
      player: str(r.player, '?'),
      position: str(r.position, '?'),
      war3yr: num(r.war3yr, 0),
      surplusWar: num(r.surplusWar, 0),
    }
  })
}

/** Lenient parse — coerces and defaults so partial responses still render. */
export function parseAnalysisReport(raw: string): AnalysisReport {
  const o = extractJsonObject(raw) as Record<string, unknown>

  const tm = o.todaysMove as Record<string, unknown> | undefined
  const report: AnalysisReport = {
    team: str(o.team, '—'),
    headline: str(o.headline, 'Strategic brief'),
    verdict: oneOf(o.verdict, VERDICTS, 'hold-and-assess'),
    confidence: clamp(num(o.confidence, 50), 0, 100),
    executiveSummary: str(o.executiveSummary, ''),

    todaysMove: tm ? {
      materiality: oneOf(tm.materiality, MATERIALITY, 'notable'),
      action: str(tm.action, 'Hold'),
      target: strN(tm.target),
      counterparty: strN(tm.counterparty),
      rationale: str(tm.rationale, ''),
      ifQuiet: str(tm.ifQuiet, ''),
    } : null,

    keyFindings: arr(o.keyFindings).map(f => {
      const r = f as Record<string, unknown>
      return { title: str(r.title, 'Finding'), detail: str(r.detail, ''), kind: oneOf(r.kind, FINDING_KINDS, 'watch') }
    }),

    recommendations: arr(o.recommendations).map((rec, i) => {
      const r = rec as Record<string, unknown>
      return {
        rank: num(r.rank, i + 1),
        action: str(r.action, 'Recommendation'),
        rationale: str(r.rationale, ''),
        targets: strArr(r.targets),
        confidence: clamp(num(r.confidence, 50), 0, 100),
        impactWar: num(r.impactWar, 0),
        horizon: oneOf(r.horizon, HORIZONS, 'deadline'),
      }
    }).sort((a, b) => a.rank - b.rank),

    proposedPackages: arr(o.proposedPackages).map(p => {
      const r = p as Record<string, unknown>
      return {
        partner: str(r.partner, '?'),
        partnerPosture: oneOf(r.partnerPosture, POSTURES, 'hold'),
        youReceive: pkgPlayers(r.youReceive),
        youSend: pkgPlayers(r.youSend),
        fillsYourHoles: strArr(r.fillsYourHoles),
        fillsTheirHoles: strArr(r.fillsTheirHoles),
        netSurplusWar: num(r.netSurplusWar, 0),
        dollarsToYouM: num(r.dollarsToYouM, 0),
        overpay: oneOf(r.overpay, OVERPAYS, 'fair'),
        likelihood: clamp(num(r.likelihood, 50), 0, 100),
        likelihoodDrivers: strArr(r.likelihoodDrivers),
        blockers: strArr(r.blockers),
        framing: str(r.framing, ''),
      }
    }),

    targetBoard: arr(o.targetBoard).map(t => {
      const r = t as Record<string, unknown>
      return {
        tier: oneOf(r.tier, TIERS, 'fallback'),
        position: str(r.position, '?'),
        player: str(r.player, '?'),
        fromTeam: str(r.fromTeam, '?'),
        controlYears: num(r.controlYears, 0),
        arbClass: str(r.arbClass, ''),
        surplusWar: num(r.surplusWar, 0),
        yr1CostM: num(r.yr1CostM, 0),
        sellerMotivation: oneOf(r.sellerMotivation, MOTIVATIONS, 'unknown'),
        likelyAsk: str(r.likelyAsk, ''),
        healthFlag: strN(r.healthFlag),
      }
    }),

    counterpartyLeverage: arr(o.counterpartyLeverage).map(c => {
      const r = c as Record<string, unknown>
      return {
        team: str(r.team, '?'),
        posture: oneOf(r.posture, POSTURES, 'hold'),
        leverageShift: clamp(num(r.leverageShift, 0), -100, 100),
        trigger: str(r.trigger, ''),
        callPriority: num(r.callPriority, 99),
        openWith: str(r.openWith, ''),
      }
    }).sort((a, b) => a.callPriority - b.callPriority),

    capImpact: arr(o.capImpact).map(c => {
      const r = c as Record<string, unknown>
      return {
        player: str(r.player, '?'),
        proratedRemainingM: num(r.proratedRemainingM, 0),
        tierAfter: tier3(r.tierAfter),
        trueDollarCostM: num(r.trueDollarCostM, 0),
        note: str(r.note, ''),
      }
    }),

    priorityMatrix: arr(o.priorityMatrix).map(m => {
      const r = m as Record<string, unknown>
      return {
        label: str(r.label, '?'),
        costM: num(r.costM, 0),
        impactWar: num(r.impactWar, 0),
        feasibility: clamp(num(r.feasibility, 50), 0, 100),
        category: oneOf(r.category, MATRIX_CATS, 'acquire'),
      }
    }),
    riskRadar: arr(o.riskRadar).map(r0 => {
      const r = r0 as Record<string, unknown>
      return { axis: str(r.axis, '?'), score: clamp(num(r.score, 50), 0, 100) }
    }),
    winProjection: arr(o.winProjection).map(w => {
      const r = w as Record<string, unknown>
      return { year: num(r.year, 2026), floor: num(r.floor, 0), expected: num(r.expected, 0), ceiling: num(r.ceiling, 0) }
    }).sort((a, b) => a.year - b.year),
    contentionTimeline: arr(o.contentionTimeline).map(c => {
      const r = c as Record<string, unknown>
      return { year: num(r.year, 2026), competitiveness: clamp(num(r.competitiveness, 50), 0, 100), note: strN(r.note) ?? undefined }
    }).sort((a, b) => a.year - b.year),

    generatedAt: new Date().toISOString(),
  }

  if (report.keyFindings.length === 0 && report.recommendations.length === 0 && report.proposedPackages.length === 0) {
    throw new Error('Parsed JSON has no findings, recommendations, or packages — check the response format.')
  }
  return report
}

// ── deterministic helpers (grounding for the prompt) ────────────────────────────

const POS_GROUPS: Record<string, string[]> = { OF: ['LF', 'CF', 'RF', 'OF'], P: ['SP', 'RP', 'P'] }
function looseMatch(a: string | null | undefined, b: string): boolean {
  if (!a) return false
  const x = a.toUpperCase(), y = b.toUpperCase()
  if (x === y) return true
  if ((POS_GROUPS[y] ?? []).includes(x)) return true
  if ((POS_GROUPS[x] ?? []).includes(y)) return true
  return false
}

function advanceArbClass(cls: ArbClass, years: number): ArbClass {
  const seq: ArbClass[] = ['pre-arb', 'arb1', 'arb2', 'arb3', 'fa']
  const i = seq.indexOf(cls)
  return seq[Math.min(i + years, seq.length - 1)]
}

const M = (v: number) => +(v / 1e6).toFixed(1)
const R1 = (v: number) => +v.toFixed(1)

function ilNote(p: CurrentPlayer): string | null {
  if (!p.status_code) return null
  if (p.status_code.toUpperCase().startsWith('D')) return p.status_desc ?? `IL (${p.status_code})`
  if (p.status_code !== 'A') return p.status_desc ?? p.status_code
  return null
}

function war3yr(p: CurrentPlayer): number {
  const age = p.age ?? 27
  let war = Math.max(0, p.last_war ?? 0)
  let sum = 0
  for (let t = 0; t < 3; t++) { war = Math.max(0, war + agingDelta(age + t)); sum += war }
  return R1(sum)
}

type AssetRow = {
  name: string; pos: string | null; age: number | null; arbClass: ArbClass
  controlYears: number; warNow: number; war3yr: number; yr1CostM: number; proratedCostM: number; il: string | null
}
function assetOf(p: CurrentPlayer, factor: number): AssetRow {
  const arb = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
  return {
    name: p.name, pos: p.position_abbr, age: p.age, arbClass: arb.currentClass,
    controlYears: arb.yearsControlled, warNow: R1(p.last_war ?? 0), war3yr: war3yr(p),
    yr1CostM: M(arb.projections[0]), proratedCostM: M(arb.projections[0] * factor), il: ilNote(p),
  }
}

/** Players on a team at one of `surplusPositions` that also fill one of `needPositions`. */
function tradeablePlayers(
  team: CurrentTeam, surplusPositions: Set<string>, needPositions: string[], factor: number,
): AssetRow[] {
  return team.players
    .filter(p =>
      (p.last_war ?? 0) > 0 &&
      [...surplusPositions].some(sp => looseMatch(p.position_abbr, sp)) &&
      needPositions.some(h => looseMatch(p.position_abbr, h)),
    )
    .sort((a, b) => (b.last_war ?? 0) - (a.last_war ?? 0))
    .slice(0, 5)
    .map(p => assetOf(p, factor))
}

export type PromptInput = {
  team: IndexTeam
  payload: TeamPayload
  rosterPlayers: CurrentPlayer[]
  buyLow: BuyLowCandidate[]
  deals: DealCandidate[]
  cbtThreshold: number
  season: number
  playoffProb: number
  allTeams?: CurrentTeam[]
  allPayloads?: Record<string, TeamPayload>
}

function projectWindow(players: CurrentPlayer[]) {
  return [...players]
    .filter(p => (p.last_war ?? 0) > 0.3 && p.age != null)
    .sort((a, b) => (b.last_war ?? 0) - (a.last_war ?? 0))
    .slice(0, 10)
    .map(p => {
      const age = p.age!
      let war = Math.max(0, p.last_war ?? 0)
      const proj: number[] = []
      for (let t = 0; t < 3; t++) { war = Math.max(0, war + agingDelta(age + t)); proj.push(R1(war)) }
      return { name: p.name, pos: p.position_abbr, age, arbClass: parseArbClass(p.contract_status), warNow: R1(p.last_war ?? 0), proj3yr: proj, il: ilNote(p) }
    })
}

function projectPayroll(players: CurrentPlayer[]) {
  return [2026, 2027, 2028].map((yr, t) => {
    let preArb = 0, arb = 0, fa = 0
    for (const p of players) {
      const f = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
      const cls = advanceArbClass(f.currentClass, t)
      const cost = f.projections[t] ?? f.projections[2]
      if (cls === 'pre-arb') preArb += cost
      else if (cls !== 'fa') arb += cost
      else fa += cost
    }
    return { year: yr, preArbM: M(preArb), arbM: M(arb), faVetM: M(fa), totalM: M(preArb + arb + fa) }
  })
}

function cbtTierOf(payroll: number, threshold: number): number {
  const over = payroll - threshold
  return over <= 0 ? 0 : over < 20e6 ? 1 : over < 40e6 ? 2 : 3
}

const SCHEMA_BLOCK = `{
  "team": "<code>",
  "headline": "<one punchy sentence — the strategic thesis>",
  "verdict": "aggressive-buy | selective-buy | hold-and-assess | soft-sell | full-teardown",
  "confidence": <0-100>,
  "executiveSummary": "<2-4 sentences. Decisive. Cite specific players/positions/numbers.>",

  "todaysMove": {                         // THE most important field — the daily diff
    "materiality": "quiet | notable | urgent",
    "action": "<the ONE concrete thing to do in the next 72h>",
    "target": "<player name or null>",
    "counterparty": "<team code or null>",
    "rationale": "<why now>",
    "ifQuiet": "<if nothing material moved, say so + name the next decision point>"
  },

  "keyFindings": [                        // 3-5
    { "title": "<short>", "detail": "<1-2 sentences>", "kind": "critical | opportunity | watch | strength" }
  ],

  "recommendations": [                    // 3-6, ranked
    { "rank": <int>, "action": "<imperative>", "rationale": "<quantified>", "targets": ["<names from data>"],
      "confidence": <0-100>, "impactWar": <net WAR, may be negative>, "horizon": "now | deadline | offseason | multi-year" }
  ],

  "proposedPackages": [                   // 2-4 FULL two-sided deals built from the package skeletons provided
    {
      "partner": "<team code>",
      "partnerPosture": "buy | hold | sell",
      "youReceive": [ { "player": "<name>", "position": "<pos>", "war3yr": <n>, "surplusWar": <n> } ],
      "youSend":    [ { "player": "<name>", "position": "<pos>", "war3yr": <n>, "surplusWar": <n> } ],
      "fillsYourHoles": ["<pos>"],
      "fillsTheirHoles": ["<pos>"],
      "netSurplusWar": <positive = your favor, negative = you overpay>,
      "dollarsToYouM": <prorated salary you take on, $M>,
      "overpay": "you-overpay | fair | you-win",
      "likelihood": <0-100>,
      "likelihoodDrivers": ["<why it clears>"],
      "blockers": ["<what could kill it: over CBT, 40-man, NTC, health>"],
      "framing": "<the one-line pitch you open the call with>"
    }
  ],

  "targetBoard": [                        // tiered acquisition board, 5-9 players
    { "tier": "primary | fallback | dart-throw", "position": "<hole>", "player": "<name>", "fromTeam": "<code>",
      "controlYears": <int>, "arbClass": "<pre-arb|arb1|arb2|arb3>", "surplusWar": <n>, "yr1CostM": <n>,
      "sellerMotivation": "forced | opportunistic | reluctant | unknown", "likelyAsk": "<what they want back>",
      "healthFlag": "<IL/role concern or null>" }
  ],

  "counterpartyLeverage": [               // who to call, in order
    { "team": "<code>", "posture": "buy | hold | sell", "leverageShift": <-100..100, negative = weakening = your opening>,
      "trigger": "<what changed their position>", "callPriority": <1-based>, "openWith": "<your first move>" }
  ],

  "capImpact": [                          // true cost of your top 3-5 acquisition candidates
    { "player": "<name>", "proratedRemainingM": <n>, "tierAfter": <0|1|2|3 CBT tier after adding>,
      "trueDollarCostM": <prorated × (1 + marginal tax)>, "note": "<escalator/repeater note>" }
  ],

  "priorityMatrix": [                     // 5-9 — every notable move plotted
    { "label": "<player/move>", "costM": <n>, "impactWar": <n>, "feasibility": <0-100>, "category": "acquire | trade-away | extend | hold" }
  ],
  "riskRadar": [                          // EXACTLY these 6 axes, 0-100 (100 = healthy)
    { "axis": "Payroll Flexibility", "score": <n> }, { "axis": "Farm Depth", "score": <n> },
    { "axis": "Age Curve", "score": <n> }, { "axis": "Positional Need", "score": <n> },
    { "axis": "Window Timing", "score": <n> }, { "axis": "Roster Risk", "score": <n> }
  ],
  "winProjection": [ { "year": 2026, "floor": <n>, "expected": <n>, "ceiling": <n> } ],   // next 4 seasons, win totals
  "contentionTimeline": [ { "year": 2026, "competitiveness": <0-100>, "note": "<optional>" } ] // 2026-2031
}`

export function buildAnalysisPrompt(input: PromptInput): string {
  const { team, payload, rosterPlayers, buyLow, deals, cbtThreshold, season, playoffProb, allTeams = [], allPayloads = {} } = input

  const gamesPlayed = team.w + team.l
  const gamesRemaining = Math.max(0, 162 - gamesPlayed)
  const factor = gamesRemaining / 162
  const myTier = cbtTierOf(team.payrollCommitted, cbtThreshold)
  const myHolePositions = payload.holes.map(h => h.position)
  const mySurplusPositions = new Set(payload.surpluses.map(s => s.position))
  const myTeam = allTeams.find(t => t.bref === team.code)

  // Two-sided package skeletons grounded in real surplus-WAR / cost figures.
  const packageSkeletons = deals.slice(0, 5).map(d => {
    const partnerTeam = allTeams.find(t => t.bref === d.partnerBref)
    const partnerPayload = allPayloads[d.partnerBref]
    const partnerSurplusPos = new Set((partnerPayload?.surpluses ?? []).map(s => s.position))
    const theirHolePos = (partnerPayload?.holes ?? []).map(h => h.position)
    return {
      partner: d.partnerBref,
      posture: d.partnerPosture,
      record: d.partnerWL,
      headroomM: M(d.partnerHeadroom),
      theyCanGiveYou: partnerTeam ? tradeablePlayers(partnerTeam, partnerSurplusPos, myHolePositions, factor) : [],
      youCanGiveThem: myTeam ? tradeablePlayers(myTeam, mySurplusPositions, theirHolePos, factor) : [],
    }
  }).filter(s => s.theyCanGiveYou.length > 0 || s.youCanGiveThem.length > 0)

  const data = {
    meta: { team: team.code, name: team.name, division: team.division, season, gamesPlayed, gamesRemaining, salaryProrationFactor: R1(factor) },
    standings: {
      record: `${team.w}-${team.l}`, winPct: +team.winPct.toFixed(3), gamesBack: team.gamesBack,
      playoffProbPct: Math.round(playoffProb * 100), posture: team.windowPosture, rationale: payload.context.postureRationale,
    },
    payroll: {
      committedM: M(team.payrollCommitted), cbtThresholdM: M(cbtThreshold), headroomM: M(team.payrollHeadroom),
      currentCbtTier: myTier, tierNote: 'tier 0=under, 1=+$20M (20% tax), 2=+$40M (32%), 3=+$60M (62.5% surtax); repeat payors face escalators',
    },
    holes: payload.holes.map(h => ({ position: h.position, severity: h.severity, holeScore: R1(h.holeScore), rosteredWar: R1(h.rosteredWar), farmWar: R1(h.farmWar) })),
    surpluses: payload.surpluses.map(s => ({ position: s.position, surplus: R1(s.surplus ?? 0) })),
    topContracts: payload.context.expiringContracts.map(c => ({ player: c.player, position: c.position, capHitM: M(c.capHit) })),
    coreWindow: projectWindow(rosterPlayers),
    payrollOutlook3yr: projectPayroll(rosterPlayers),
    yourTradeableAssets: myTeam ? tradeablePlayers(myTeam, mySurplusPositions, [...mySurplusPositions], factor) : [],
    buyLowTargets: buyLow.map(b => ({
      name: b.player.name, team: b.sourceTeam.bref, teamPosture: b.sourcePosture, position: b.player.position_abbr,
      age: b.player.age, surplusWar: R1(b.surplusWar), yr1CostM: M(b.yr1Cost), yearsControlled: b.yearsControlled,
      fillsHoles: b.holesFilled.map(h => h.position), il: ilNote(b.player),
    })),
    dealsThatClear: deals.map(d => ({
      partner: d.partnerBref, posture: d.partnerPosture, record: d.partnerWL, headroomM: M(d.partnerHeadroom),
      theyGiveYou: d.theyFill.map(h => h.position), youGiveThem: d.youFill.map(h => h.position),
    })),
    packageSkeletons,
  }

  return `You are an elite MLB President of Baseball Operations advisor briefing the ${team.name} front office. This is a DAILY war-room brief at the trade deadline. Six desks rely on it: the analytics POBO (wants the marginal EV-maximizing move), the veteran GM (wants counterparty sequencing — whose leverage is collapsing), the pro scouting director (wants health/role vetoes — never recommend a hurt player), the capology desk (wants prorated true cost + CBT tier escalators), the AGM running the trade board (wants tiered targets + real packages with fallbacks), and the manager liaison (wants lineup/handedness fit, not abstract "need").

WAR is the currency. Salaries are arbitration-projected. "surplusWar" already nets out projected salary. Aging curves are applied to multi-year projections. Costs marked prorated reflect ${gamesRemaining} of 162 games remaining (factor ${R1(factor)}).

== WAR ROOM DATA ==
${JSON.stringify(data, null, 2)}

== HOW TO THINK (channel the six desks) ==
- todaysMove is the headline. The verdict barely moves day to day — the daily value is the DIFF and the single best action right now. If nothing material moved, set materiality:"quiet" and say so plainly in ifQuiet with the next real decision point.
- proposedPackages: build 2-4 ACTUAL two-sided deals from the packageSkeletons above. Use only the named players in those skeletons. Balance them: net surplus WAR within ±1.5 is "fair"; beyond that flag overpay. SEND BLOCKED/REDUNDANT controllable players, never your stars. Respect the partner's headroom. Write the framing line you'd actually open the call with.
- targetBoard: tier the buyLowTargets (primary / fallback / dart-throw) so the AGM has costed fallbacks ready. Add sellerMotivation and likelyAsk. If a target has an "il" flag, surface it as healthFlag and DO NOT make it a primary.
- counterpartyLeverage: from postures, records, and headroom, rank who to call first and what to open with. Forced sellers and headroom-rich buyers move first.
- capImpact: for your top acquisition candidates, compute prorated remaining $ and whether it pushes you into a higher CBT tier; note repeater/escalator risk.
- Be specific and quantified everywhere. Generic advice is worthless to this room.

== OUTPUT FORMAT ==
Return ONLY one JSON object matching this schema exactly. No prose, no markdown fences.

${SCHEMA_BLOCK}

RULES:
- Use ONLY player names that appear in the data above.
- impactWar/netSurplusWar: net WAR; trade-aways and bad holds can be negative.
- riskRadar: all 6 axes, 100 = strong/healthy.
- winProjection: realistic win totals — a ${gamesPlayed}-game pace implies ~${Math.round(team.winPct * 162)} full-season wins as the 2026 expected baseline.
- Vary confidence to reflect genuine uncertainty. Return valid, parseable JSON.

== DELIVERY — UPLOAD IT, DO NOT PASTE ==
Deliver the brief by putting it where the app picks it up automatically. Do not print the JSON into chat for manual pasting unless you truly have no other option.

1) PREFERRED — file drop (works in Claude Code or any environment with file-write access to the savage-trade-evaluator repo):
   Write ONLY the JSON object to:
     frontend/public/brief-inbox/${team.code}.json
   (create the folder if it does not exist; overwrite if present). The running app polls this path every ~3s and renders the brief automatically. Confirm the write — that file IS the delivery.

2) ALTERNATIVE — persist to DuckDB (the project's source of truth): if you have repo + shell access, write the JSON to a file then run:
     uv run ste brief ingest ${team.code} --file <path-to-json> --source app
   This upserts the \`war_room_briefs\` DuckDB table AND writes frontend/public/brief-inbox/${team.code}.json, so the brief is both persisted and rendered. Re-emit any time with \`uv run ste brief export --team ${team.code}\`.

3) LAST RESORT — if you have neither file nor DB access (e.g. a plain chat window): output the raw JSON object so it can be pasted into the app's manual box.`
}
