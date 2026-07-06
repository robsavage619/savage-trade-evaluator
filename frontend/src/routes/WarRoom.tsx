import { useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Sparkles, Target, Loader2 } from 'lucide-react'
import { useIdentityStore } from '../lib/identityStore'
import { warRoomIndex, loadTeamPayload, loadAllTeamPayloads } from '../lib/warroomData'
import type { TeamPayload } from '../data/warroom/types'
import { TeamLogo } from '../components/TeamLogo'
import { DEV_SIGNATURE } from '../lib/hypothetical'
import { useRoster } from '../lib/rosterStore'
import { computeDeals } from '../lib/dealsEngine'
import { computeBuyLow } from '../lib/buyLowEngine'
import { computePlayoffProb, money } from './warroom/shared'
import { Cite, SectionHeader, PulseDot } from './warroom/primitives'
import { PostureBanner } from './warroom/PostureBanner'
import { PayrollGauge, PayrollTimeline } from './warroom/PayrollSection'
import { PositionRadar, HolesBoard } from './warroom/RosterShape'
import { LeagueTicker } from './warroom/LeagueTicker'
import { PartnerPanel } from './warroom/PartnerPanel'
import { TradeWorkshop } from './warroom/TradeWorkshop'
import { WindowClock } from './warroom/WindowClock'
import { PositionMarketScan, DealsThatClear } from './warroom/IntelligenceFeed'
import { AiBrief } from './warroom/AiBrief'

// ── snapshot age utilities ────────────────────────────────────────────────────

function snapshotAgeDays(iso: string): number {
  return Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
}

type FreshnessTier = 'live' | 'stale' | 'old'
function freshnessTier(ageDays: number): FreshnessTier {
  if (ageDays < 3) return 'live'
  if (ageDays < 14) return 'stale'
  return 'old'
}
const FRESHNESS_COLORS: Record<FreshnessTier, { dot: string; text: string; border: string }> = {
  live:  { dot: 'bg-positive-500', text: 'text-positive-400', border: 'border-ink-700' },
  stale: { dot: 'bg-amber-500',    text: 'text-amber-400',    border: 'border-amber-700' },
  old:   { dot: 'bg-red-500',      text: 'text-red-400',      border: 'border-red-700' },
}

// ── main ───────────────────────────────────────────────────────────────────────

export default function WarRoom() {
  const active = useIdentityStore(s => s.activeTeam)
  const roster = useRoster()
  const [yourPayload, setYourPayload] = useState<TeamPayload | null>(null)
  const [partnerBref, setPartnerBref] = useState<string | null>(null)
  const [partnerPayload, setPartnerPayload] = useState<TeamPayload | null>(null)
  const [allPayloads, setAllPayloads] = useState<Record<string, TeamPayload> | null>(null)
  const [phase2Open, setPhase2Open] = useState(false)
  const phase2Loading = phase2Open && !allPayloads

  useEffect(() => {
    let alive = true
    setYourPayload(null)
    loadTeamPayload(active).then(p => { if (alive) setYourPayload(p) })
    return () => { alive = false }
  }, [active])

  useEffect(() => {
    if (!partnerBref) { setPartnerPayload(null); return }
    let alive = true
    setPartnerPayload(null)
    loadTeamPayload(partnerBref).then(p => { if (alive) setPartnerPayload(p) })
    return () => { alive = false }
  }, [partnerBref])

  // Lazy-load all 30 payloads when Phase 2 panel is opened
  useEffect(() => {
    if (!phase2Open || allPayloads) return
    loadAllTeamPayloads().then(all => setAllPayloads(all))
  }, [phase2Open, allPayloads])

  const devMul = DEV_SIGNATURE[active] ?? 1.0

  const deals = useMemo(() =>
    yourPayload && allPayloads ? computeDeals(active, yourPayload, allPayloads) : [],
    [active, yourPayload, allPayloads],
  )

  const buyLow = useMemo(() =>
    yourPayload && allPayloads
      ? computeBuyLow(active, yourPayload, roster.teams, allPayloads, devMul)
      : [],
    [active, yourPayload, allPayloads, roster.teams, devMul],
  )

  const indexTeam = warRoomIndex.teams.find(t => t.code === active)
  if (!indexTeam) return (
    <div className="mx-auto max-w-[1480px] px-6 py-10 font-mono text-[12px] text-ink-500">
      No data for {active}.
    </div>
  )

  const headroom = indexTeam.payrollHeadroom
  const ctx = yourPayload?.context

  const teamPlayers = roster.teams.find(t => t.bref === active)?.players ?? []

  return (
    <div className="mx-auto max-w-[1480px] px-4 py-6">
      {/* Page header */}
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <TeamLogo team={active} size={44} />
          <div>
            <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.25em] text-accent-400">
              WAR ROOM · SEASON INTELLIGENCE
            </div>
            <h1 className="display text-[30px] font-black leading-tight tracking-tight text-ink-100">
              {indexTeam.name}
            </h1>
            <div className="font-mono text-[10px] text-ink-400">{indexTeam.division}</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="font-mono text-right text-[10px] text-ink-400">
            <div>{warRoomIndex.season} SEASON · {warRoomIndex.asOfGames} GP</div>
            <div className="text-ink-500">blend w₂₀₂₆={warRoomIndex.blendWeight.toFixed(2)}</div>
          </div>
          {(() => {
            const ageDays = snapshotAgeDays(warRoomIndex.generatedAt)
            const tier = freshnessTier(ageDays)
            const fc = FRESHNESS_COLORS[tier]
            const label = tier === 'live' ? 'LIVE' : `${ageDays}d old`
            const dateLabel = new Date(warRoomIndex.generatedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
            return (
              <div className="text-right">
                <div className={`flex items-center gap-1.5 rounded-md border ${fc.border} bg-ink-900 px-2.5 py-1.5`}>
                  <PulseDot color={fc.dot} />
                  <span className={`font-mono text-[9px] font-semibold ${fc.text}`}>{label}</span>
                </div>
                <div className="mt-0.5 font-mono text-[8px] text-ink-600">snapshot {dateLabel}</div>
              </div>
            )
          })()}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[240px_1fr]">
        {/* Left: league board */}
        <aside className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
          <div className="mb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
            30-team board · click to analyze
          </div>
          <LeagueTicker yourBref={active} partnerBref={partnerBref} onSelect={setPartnerBref} />
        </aside>

        {/* Right: main intel */}
        <div className="min-w-0 space-y-4">
          <AnimatePresence mode="wait">
            {yourPayload ? (
              <motion.div key={active} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">

                {/* 1 — Posture banner (record + GB embedded) */}
                <PostureBanner
                  posture={indexTeam.windowPosture}
                  rationale={ctx?.postureRationale ?? ''}
                  playoffProb={computePlayoffProb(indexTeam.w, indexTeam.l, indexTeam.gamesBack)}
                  w={indexTeam.w}
                  l={indexTeam.l}
                  gamesBack={indexTeam.gamesBack}
                />

                {/* 2 — Payroll intelligence */}
                <div className="space-y-3">
                  <SectionHeader label="Payroll Intelligence" cite={{ label: 'Heuristic layer', detail: 'Pre-model. In-season stats shrunk toward 2025 prior. Contextual posteriors: Phase 2.' }} />
                  <PayrollGauge
                    committed={indexTeam.payrollCommitted}
                    threshold={warRoomIndex.cbtThreshold}
                    headroom={headroom}
                  />
                  {ctx && ctx.expiringContracts.length > 0 ? (
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
                        <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
                          Top commitments
                        </div>
                        <div className="space-y-1.5">
                          {ctx.expiringContracts.map((c, i) => (
                            <motion.div
                              key={c.player}
                              initial={{ opacity: 0, x: -6 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: i * 0.04 }}
                              className="flex items-center justify-between gap-2"
                            >
                              <span className="truncate text-[11px] text-ink-200">{c.player}</span>
                              {c.position && (
                                <span className="shrink-0 rounded bg-ink-800 px-1 py-0.5 font-mono text-[9px] text-ink-400">
                                  {c.position}
                                </span>
                              )}
                              <span className="font-mono shrink-0 text-[11px] tabular text-ink-300">
                                {money(c.capHit)}
                              </span>
                            </motion.div>
                          ))}
                        </div>
                      </div>
                      <PayrollTimeline players={teamPlayers} cbtThreshold={warRoomIndex.cbtThreshold} />
                    </div>
                  ) : (
                    <PayrollTimeline players={teamPlayers} cbtThreshold={warRoomIndex.cbtThreshold} />
                  )}
                </div>

                {/* 3 — Roster shape: positional radar + holes/surpluses unified */}
                <div className="space-y-3">
                  <SectionHeader label="Roster Shape" />
                  <div className="grid gap-4 md:grid-cols-2">
                    <PositionRadar
                      holes={yourPayload.holes}
                      surpluses={yourPayload.surpluses}
                      posture={indexTeam.windowPosture}
                    />
                    <HolesBoard
                      holes={yourPayload.holes}
                      surpluses={yourPayload.surpluses}
                    />
                  </div>
                </div>

                {/* 4 — Contention window */}
                <div className="space-y-3">
                  <SectionHeader label="Contention Window" cite={{ label: 'Contention Window', detail: 'Projected WAR for top-10 contributors by year, applying the aging curve (delta-method). Dev-system multiplier not applied — raw age trajectory only. Arb class shows cost escalation path.' }} />
                  <WindowClock players={teamPlayers} />
                </div>

                {/* 5 — Intelligence feed (always visible, not gated by partner selection) */}
                <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-3.5 w-3.5 text-accent-400" />
                      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-300">
                        Intelligence Feed
                      </span>
                      <Cite cite={{ label: 'Intelligence Feed', detail: 'Buy-low targets: players on sellers whose surplus WAR fills your positional holes. Deals that clear: teams where your surpluses fill their holes and vice versa — mutual fit.' }} />
                    </div>
                    {!phase2Open ? (
                      <button
                        onClick={() => setPhase2Open(true)}
                        className="rounded border border-accent-500/40 bg-accent-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-accent-300 transition-colors hover:bg-accent-500/20"
                      >
                        LOAD ANALYSIS
                      </button>
                    ) : phase2Loading ? (
                      <span className="font-mono text-[9px] text-ink-500">Loading 30 teams…</span>
                    ) : null}
                  </div>
                  {!phase2Open ? (
                    <div className="flex items-center gap-3 py-3">
                      <Sparkles className="h-5 w-5 text-accent-400/40 shrink-0" />
                      <p className="text-[11px] leading-relaxed text-ink-400">
                        Cross-reference all 30 rosters for buy-low targets and mutual trade fits.
                        <span className="ml-1 text-accent-300">Load analysis to activate.</span>
                      </p>
                    </div>
                  ) : phase2Loading ? (
                    <div className="flex items-center gap-2 py-4 font-mono text-[11px] text-ink-500">
                      <motion.span animate={{ opacity: [0.4, 1, 0.4] }} transition={{ repeat: Infinity, duration: 1.2 }}>
                        Scanning league…
                      </motion.span>
                    </div>
                  ) : (
                    <div className="grid gap-5 md:grid-cols-2">
                      <div>
                        <div className="mb-2 flex items-center gap-1.5">
                          <Sparkles className="h-3 w-3 text-positive-400" />
                          <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-positive-400">
                            Position Market Scan
                          </span>
                          <span className="font-mono text-[8.5px] text-ink-500">by hole · control-window surplus WAR</span>
                        </div>
                        <PositionMarketScan candidates={buyLow} holes={yourPayload.holes} />
                      </div>
                      <div>
                        <div className="mb-2 flex items-center gap-1.5">
                          <Target className="h-3 w-3 text-accent-400" />
                          <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-accent-400">
                            Deals that clear
                          </span>
                          <span className="font-mono text-[8.5px] text-ink-500">mutual hole/surplus match</span>
                        </div>
                        <DealsThatClear deals={deals} onSelect={setPartnerBref} />
                      </div>
                    </div>
                  )}
                </div>

                {/* 6 — Partner panel + trade workshop (co-located) */}
                <AnimatePresence>
                  {partnerBref && (
                    <motion.div
                      key={`partner-${partnerBref}`}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 10 }}
                      className="space-y-4"
                    >
                      <PartnerPanel
                        bref={partnerBref}
                        payload={partnerPayload}
                        onClose={() => setPartnerBref(null)}
                      />
                      <TradeWorkshop
                        yourBref={active}
                        partnerBref={partnerBref}
                        verdictCtx={{
                          yourPosture: indexTeam.windowPosture,
                          playoffProb: computePlayoffProb(indexTeam.w, indexTeam.l, indexTeam.gamesBack),
                          currentW: indexTeam.w,
                          currentL: indexTeam.l,
                          gamesBack: indexTeam.gamesBack,
                        }}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* 7 — AI intelligence brief (always mounted) */}
                <AiBrief
                  promptInput={{
                    team: indexTeam,
                    payload: yourPayload,
                    rosterPlayers: teamPlayers,
                    buyLow,
                    deals,
                    cbtThreshold: warRoomIndex.cbtThreshold,
                    season: warRoomIndex.season,
                    playoffProb: computePlayoffProb(indexTeam.w, indexTeam.l, indexTeam.gamesBack),
                    allTeams: roster.teams,
                    allPayloads: allPayloads ?? {},
                  }}
                />

              </motion.div>
            ) : (
              <div className="flex items-center justify-center gap-2 py-20 font-mono text-[11px] text-ink-600">
                <Loader2 className="h-4 w-4 animate-spin text-accent-400" />
                Loading {active} intel…
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
