import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowLeftRight, Brain, Terminal, Trash2, BadgePlus, Coins, Gauge, TrendingUp, TrendingDown, XCircle, Minus } from 'lucide-react'
import { type CurrentPlayer, type CurrentTeam } from '../data/players'
import { useRoster, useTeamsByBref } from '../lib/rosterStore'
import { useIdentityStore, TEAM_THEME } from '../lib/identityStore'
import { TeamIdentitySwitcher } from '../components/TeamIdentitySwitcher'
import { PlayerPicker, BasketCard } from '../components/PlayerPicker'
import { RefreshRostersButton } from '../components/RefreshRostersButton'
import { PosteriorViolin } from '../components/PosteriorViolin'
import { Section, Stat } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import { computeVerdict, type Verdict } from '../lib/hypothetical'
import { composeHypotheticalPrompt } from '../lib/composeHypothetical'
import { fmtSigned, fmtMoney } from '../lib/format'
import { forecastArb, isControlled } from '../lib/arbForecast'
import { useReasoningStore, parseReasoningResponse } from '../lib/reasoningStore'
import { AnimatePresence } from 'framer-motion'
import { X, Copy, ClipboardCheck, AlertCircle, CheckCircle2, RotateCcw, Sparkles } from 'lucide-react'

/** Pseudo-id namespace for hypothetical trades — kept negative to avoid colliding
 *  with real trade_event_ids. */
const HYPO_BASE = -1_000_000

type SignalEntry = { label: string; Icon: React.ElementType; color: string; bg: string; border: string; glyph: string }
const SIGNAL_CONFIG: Record<Verdict['recommendation'], SignalEntry> = {
  'strong-buy':  { label: 'ACCEPT THIS TRADE',      Icon: CheckCircle2, color: 'text-positive-500', bg: 'bg-positive-500/10',     border: 'border-positive-500/30', glyph: '✓' },
  'lean-buy':    { label: 'LEAN ACCEPT',             Icon: TrendingUp,   color: 'text-positive-500', bg: 'bg-positive-500/[0.06]', border: 'border-positive-500/20', glyph: '↑' },
  'neutral':     { label: 'HOLD — REQUEST COUNTER',  Icon: Minus,        color: 'text-ink-200',      bg: 'bg-ink-700/20',          border: 'border-ink-600/30',      glyph: '—' },
  'lean-pass':   { label: 'COUNTER OR WALK',         Icon: TrendingDown, color: 'text-accent-400',   bg: 'bg-accent-500/[0.06]',  border: 'border-accent-500/20',   glyph: '↓' },
  'strong-pass': { label: 'DO NOT ACCEPT',           Icon: XCircle,      color: 'text-negative-500', bg: 'bg-negative-500/10',    border: 'border-negative-500/30', glyph: '✗' },
}

function TradeComparison({
  sendingPlayers,
  receivingPlayers,
  yourBref,
  partnerBref,
  verdict,
}: {
  sendingPlayers: CurrentPlayer[]
  receivingPlayers: CurrentPlayer[]
  yourBref: string
  partnerBref: string
  verdict: Verdict
}) {
  const allWars = [...sendingPlayers, ...receivingPlayers].map((p) => p.last_war ?? 0.5)
  const maxWar = Math.max(...allWars, 1)

  const allSalaries = [...sendingPlayers, ...receivingPlayers].map((p) => p.last_salary ?? 1_500_000)
  const maxSalary = Math.max(...allSalaries, 1_500_000)

  const rawWarSent = sendingPlayers.reduce((a, p) => a + (p.last_war ?? 0.5), 0)
  const rawWarReceived = receivingPlayers.reduce((a, p) => a + (p.last_war ?? 0.5), 0)
  const warDelta = rawWarReceived - rawWarSent

  function PlayerRow({ player, side }: { player: CurrentPlayer; side: 'sent' | 'received' }) {
    const war = player.last_war ?? 0.5
    const salary = player.last_salary ?? 1_500_000
    const warPct = Math.max(0, Math.min(1, war / maxWar))
    const salaryPct = Math.max(0, Math.min(1, salary / maxSalary))
    const barColor = side === 'received' ? 'bg-positive-500/70' : 'bg-negative-500/50'
    const salaryBarColor = side === 'received' ? 'bg-baseline-500/50' : 'bg-ink-500/60'
    const arb = forecastArb(player.contract_status, player.last_war, player.cap_hit)
    const showRamp = isControlled(arb.currentClass)
    const rampColor = side === 'received' ? 'bg-positive-500' : 'bg-ink-400'
    const maxRamp = Math.max(...arb.projections, salary)
    return (
      <div className="rounded-md border border-ink-700 bg-ink-800/40 px-3 py-2.5">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="truncate text-[13px] font-semibold text-ink-100">{player.name}</span>
            {player.position_abbr && (
              <span className="shrink-0 rounded bg-ink-700 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-ink-300">
                {player.position_abbr}
              </span>
            )}
            {showRamp && (
              <span className="shrink-0 rounded bg-accent-500/15 px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-accent-400">
                {arb.currentClass === 'pre-arb' ? 'Pre-Arb' : arb.currentClass.toUpperCase()} · {arb.yearsControlled}yr ctrl
              </span>
            )}
          </div>
          <span className={`mono shrink-0 text-[12px] font-semibold tabular ${side === 'received' ? 'text-positive-500' : 'text-negative-500'}`}>
            {war >= 0 ? '+' : ''}{war.toFixed(1)} WAR
          </span>
        </div>
        {/* WAR bar */}
        <div className="mb-1 h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
          <div className={`h-full rounded-full transition-all ${barColor}`} style={{ width: `${warPct * 100}%` }} />
        </div>
        {/* Salary bar */}
        <div className="flex items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-700/60">
            <div className={`h-full rounded-full ${salaryBarColor}`} style={{ width: `${salaryPct * 100}%` }} />
          </div>
          <span className="mono shrink-0 text-[10px] text-ink-400">{fmtMoney(salary)}</span>
        </div>
        {/* Arb salary ramp (only for cost-controlled players) */}
        {showRamp && (
          <div className="mt-2 border-t border-ink-700/50 pt-2">
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-[0.14em] text-ink-500">Projected arb cost ramp</div>
            <div className="flex gap-2">
              {arb.projections.map((proj, i) => {
                const pct = Math.max(0.04, proj / maxRamp)
                const label = ['Yr+1', 'Yr+2', 'Yr+3'][i]
                return (
                  <div key={i} className="flex flex-1 flex-col items-center gap-0.5">
                    <div className="flex w-full flex-col justify-end" style={{ height: 20 }}>
                      <div
                        className={`w-full rounded-sm ${rampColor} opacity-60`}
                        style={{ height: `${pct * 100}%`, minHeight: 3 }}
                      />
                    </div>
                    <span className="mono text-[8px] text-ink-500">{label}</span>
                    <span className="mono text-[9px] font-medium text-ink-300">{fmtMoney(proj)}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">Player-by-player comparison</div>
      <div className="grid gap-4 md:grid-cols-2">
        {/* Sending */}
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-negative-500">
            <span className="h-1.5 w-1.5 rounded-full bg-negative-500/70" />
            {yourBref} sends ({sendingPlayers.length})
          </div>
          <div className="space-y-2">
            {sendingPlayers.length > 0
              ? sendingPlayers.map((p) => <PlayerRow key={p.mlb_player_id} player={p} side="sent" />)
              : <div className="rounded-md border border-dashed border-ink-700 p-3 text-[12px] text-ink-500">No players selected</div>
            }
          </div>
          {sendingPlayers.length > 0 && (
            <div className="mt-2 flex items-center justify-between rounded-md bg-ink-700/30 px-3 py-1.5">
              <span className="text-[10px] uppercase tracking-[0.14em] text-ink-400">Total</span>
              <div className="flex items-center gap-4">
                <span className="mono text-[12px] font-semibold text-negative-500">−{rawWarSent.toFixed(1)} WAR</span>
                <span className="mono text-[12px] text-ink-300">{fmtMoney(verdict.costSent)}</span>
              </div>
            </div>
          )}
        </div>

        {/* Receiving */}
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-positive-500">
            <span className="h-1.5 w-1.5 rounded-full bg-positive-500/70" />
            {yourBref} receives ({receivingPlayers.length})
          </div>
          <div className="space-y-2">
            {receivingPlayers.length > 0
              ? receivingPlayers.map((p) => <PlayerRow key={p.mlb_player_id} player={p} side="received" />)
              : <div className="rounded-md border border-dashed border-ink-700 p-3 text-[12px] text-ink-500">No players selected</div>
            }
          </div>
          {receivingPlayers.length > 0 && (
            <div className="mt-2 flex items-center justify-between rounded-md bg-ink-700/30 px-3 py-1.5">
              <span className="text-[10px] uppercase tracking-[0.14em] text-ink-400">Total</span>
              <div className="flex items-center gap-4">
                <span className="mono text-[12px] font-semibold text-positive-500">+{rawWarReceived.toFixed(1)} WAR</span>
                <span className="mono text-[12px] text-ink-300">{fmtMoney(verdict.costReceived)}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Balance bar */}
      {sendingPlayers.length > 0 && receivingPlayers.length > 0 && (
        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-[0.14em] text-ink-400">
            <span>{yourBref} sends more</span>
            <span className={`mono font-semibold ${warDelta >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>
              Net WAR: {warDelta >= 0 ? '+' : ''}{warDelta.toFixed(1)}
            </span>
            <span>{partnerBref} sends more</span>
          </div>
          <div className="relative h-3 overflow-hidden rounded-full bg-ink-700">
            <div className="absolute inset-0 flex">
              {/* Left half = sent (red) */}
              <div className="h-full w-1/2">
                <div
                  className="absolute right-1/2 h-full bg-negative-500/60 rounded-l-full transition-all"
                  style={{ width: `${Math.min(50, (rawWarSent / (rawWarSent + rawWarReceived || 1)) * 100)}%` }}
                />
              </div>
              {/* Right half = received (green) */}
              <div className="h-full w-1/2">
                <div
                  className="absolute left-1/2 h-full bg-positive-500/60 rounded-r-full transition-all"
                  style={{ width: `${Math.min(50, (rawWarReceived / (rawWarSent + rawWarReceived || 1)) * 100)}%` }}
                />
              </div>
            </div>
            {/* Center line */}
            <div className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-ink-500" />
          </div>
        </div>
      )}
    </div>
  )
}

export default function TradeBuilder() {
  const yourBref = useIdentityStore((s) => s.activeTeam)
  const roster = useRoster()
  const teamsByBref = useTeamsByBref()
  const yourTeam = teamsByBref[yourBref] ?? teamsByBref.NYM
  const theme = TEAM_THEME[yourBref] ?? TEAM_THEME.NYM
  const [partnerBref, setPartnerBref] = useState<string>('TBR')
  const partnerTeam = teamsByBref[partnerBref] ?? teamsByBref.TBR

  const [sentIds, setSentIds] = useState<number[]>([])
  const [receivedIds, setReceivedIds] = useState<number[]>([])

  const sendingPlayers = useMemo<CurrentPlayer[]>(
    () => sentIds.map((id) => yourTeam.players.find((p) => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [sentIds, yourTeam],
  )
  const receivingPlayers = useMemo<CurrentPlayer[]>(
    () => receivedIds.map((id) => partnerTeam.players.find((p) => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [receivedIds, partnerTeam],
  )

  const verdict = useMemo(
    () => computeVerdict({ sending: { team: yourTeam, players: sendingPlayers }, receiving: { team: partnerTeam, players: receivingPlayers } }),
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers],
  )

  function addToSent(p: CurrentPlayer, t: CurrentTeam) {
    if (t.bref !== yourBref) return // ignore if user picks from non-self
    if (sentIds.includes(p.mlb_player_id)) return
    setSentIds([...sentIds, p.mlb_player_id])
  }
  function addToReceived(p: CurrentPlayer, t: CurrentTeam) {
    if (t.bref !== partnerBref) setPartnerBref(t.bref)
    if (receivedIds.includes(p.mlb_player_id)) return
    setReceivedIds((prev) => [...prev, p.mlb_player_id])
  }
  function removeSent(id: number) { setSentIds((s) => s.filter((x) => x !== id)) }
  function removeReceived(id: number) { setReceivedIds((s) => s.filter((x) => x !== id)) }

  function swapSides() {
    // swap rosters — your team becomes partner, partner becomes you
    const oldPartner = partnerBref
    const oldSent = sentIds
    const oldReceived = receivedIds
    setPartnerBref(yourBref)
    // change identity store
    useIdentityStore.getState().setActiveTeam(oldPartner)
    setSentIds(oldReceived)
    setReceivedIds(oldSent)
  }

  const selectedAllIds = useMemo(() => new Set<number>([...sentIds, ...receivedIds]), [sentIds, receivedIds])

  // Claude Code drawer state
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)
  const [pasteOk, setPasteOk] = useState(false)
  const [copied, setCopied] = useState(false)
  const hypoId = useMemo(() => {
    // Stable-ish id from the selection signature so saved analyses survive across the same hypothetical
    const sig = `${yourBref}|${partnerBref}|${[...sentIds].sort().join(',')}|${[...receivedIds].sort().join(',')}`
    let h = 0
    for (let i = 0; i < sig.length; i++) h = (h * 31 + sig.charCodeAt(i)) | 0
    return HYPO_BASE - Math.abs(h)
  }, [yourBref, partnerBref, sentIds, receivedIds])

  const override = useReasoningStore((s) => s.overrides[hypoId])
  const setReasoning = useReasoningStore((s) => s.set)

  const prompt = useMemo(
    () => verdict ? composeHypotheticalPrompt({ yourTeam, partnerTeam, sending: sendingPlayers, receiving: receivingPlayers, verdict }) : '',
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers, verdict],
  )

  async function copyPrompt() {
    if (!prompt) return
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  function applyPaste() {
    setPasteError(null)
    setPasteOk(false)
    const r = parseReasoningResponse(pasteText)
    if ('error' in r) {
      setPasteError(r.error)
      return
    }
    setReasoning(hypoId, r, 'Claude Code · hypothetical')
    setPasteOk(true)
  }

  return (
    <main className="mx-auto max-w-[1640px] px-6 py-6">
      {/* Top control band */}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="card mb-5 overflow-hidden"
      >
        <div
          className="h-1 w-full"
          style={{ background: `linear-gradient(90deg, ${theme.primary}, ${theme.secondary})` }}
          aria-hidden
        />
        <div className="flex flex-wrap items-center justify-between gap-4 p-4">
          <div className="flex items-center gap-3">
            <TeamLogo team={yourBref} size={40} />
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Trade Builder · You are</div>
              <div className="text-[16px] font-semibold tracking-tight text-ink-100">{yourTeam.name}</div>
              <div className="text-[11px] text-ink-400">Workshop a hypothetical against any club. All verdicts framed from {yourBref}'s side.</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <RefreshRostersButton />
            <span className="hidden h-6 w-px bg-ink-700 md:block" />
            <TeamIdentitySwitcher />
            <span className="hidden h-6 w-px bg-ink-700 md:block" />
            <button
              onClick={swapSides}
              className="inline-flex items-center gap-1.5 rounded-md border border-ink-700 px-2.5 py-1.5 text-[11px] font-medium text-ink-200 transition-colors hover:border-accent-500/60 hover:text-ink-100"
              title="Flip identities — see the deal from the other GM's seat"
            >
              <ArrowLeftRight className="h-3 w-3" /> Flip sides
            </button>
            <button
              onClick={() => { setSentIds([]); setReceivedIds([]) }}
              className="inline-flex items-center gap-1.5 rounded-md border border-ink-700 px-2.5 py-1.5 text-[11px] font-medium text-ink-300 transition-colors hover:border-negative-500/60 hover:text-negative-500"
            >
              <Trash2 className="h-3 w-3" /> Clear baskets
            </button>
          </div>
        </div>
      </motion.div>

      {/* Verdict band */}
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="card mb-6 overflow-hidden">
        {verdict ? (() => {
          const signal = SIGNAL_CONFIG[verdict.recommendation]
          const SignalIcon = signal.Icon
          const rawWarSent = sendingPlayers.reduce((a, p) => a + (p.last_war ?? 0.5), 0)
          const rawWarReceived = receivingPlayers.reduce((a, p) => a + (p.last_war ?? 0.5), 0)
          const dollarPerWarSent = rawWarSent > 0 ? verdict.costSent / rawWarSent / 1_000_000 : null
          const dollarPerWarReceived = rawWarReceived > 0 ? verdict.costReceived / rawWarReceived / 1_000_000 : null
          const salaryDelta = verdict.costReceived - verdict.costSent
          const receivedArbTotal = receivingPlayers.reduce((acc, p) => {
            const a = forecastArb(p.contract_status, p.last_war, p.cap_hit)
            return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
          }, 0)
          const sentArbTotal = sendingPlayers.reduce((acc, p) => {
            const a = forecastArb(p.contract_status, p.last_war, p.cap_hit)
            return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
          }, 0)
          return (
            <>
              {/* GM Signal Banner */}
              <div className={`border-b px-5 py-4 ${signal.bg} ${signal.border}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className={`grid h-12 w-12 shrink-0 place-items-center rounded-full border-2 ${signal.border}`}>
                      <SignalIcon className={`h-6 w-6 ${signal.color}`} strokeWidth={2.5} />
                    </div>
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">GM Decision Signal · {yourBref} perspective</div>
                      <div className={`text-[26px] font-bold tracking-tight leading-tight ${signal.color}`}>{signal.label}</div>
                      <div className="text-[12px] text-ink-400">{verdict.recommendationLabel} · dev-multiplier {verdict.acquirerDevMultiplier.toFixed(2)}× applied to incoming players</div>
                    </div>
                  </div>
                  <div className={`select-none font-black leading-none ${signal.color} opacity-[0.13]`} style={{ fontSize: 72 }}>{signal.glyph}</div>
                </div>
              </div>

              {/* Metrics row */}
              <div className="flex flex-wrap items-end justify-between gap-6 p-5">
                <div className="flex flex-wrap items-end gap-7">
                  <Stat label="3-yr surplus" value={fmtSigned(verdict.surplusMean)} sub={`90% [${verdict.surplusLo.toFixed(2)}, ${verdict.surplusHi.toFixed(2)}]`} tone={verdict.reasoningTone} />
                  <Stat label="P(accept)" value={`${Math.round(verdict.pPositive * 100)}%`} sub="Posterior > 0" tone={verdict.reasoningTone} />
                  <Stat label="WAR in (adj)" value={`+${verdict.warReceived.toFixed(1)}`} sub={`raw ${rawWarReceived.toFixed(1)} × dev ${verdict.acquirerDevMultiplier.toFixed(2)}×`} tone="pos" />
                  <Stat label="WAR out (adj)" value={`−${verdict.warSent.toFixed(1)}`} sub={`partner dev-adjusted`} tone="neg" />
                  <Stat label="Net WAR Δ" value={fmtSigned(verdict.warReceived - verdict.warSent, 1)} sub="dev-adjusted" tone={verdict.reasoningTone} />
                  <Stat label="Salary Δ" value={`${salaryDelta <= 0 ? '−' : '+'}${fmtMoney(Math.abs(salaryDelta))}`} sub={`In ${fmtMoney(verdict.costReceived)} · Out ${fmtMoney(verdict.costSent)}`} tone={salaryDelta <= 0 ? 'pos' : 'neg'} />
                  {dollarPerWarSent != null && <Stat label="$/WAR out" value={`$${dollarPerWarSent.toFixed(1)}M`} sub="cost/WAR of players sent" tone="neutral" />}
                  {dollarPerWarReceived != null && <Stat label="$/WAR in" value={`$${dollarPerWarReceived.toFixed(1)}M`} sub={dollarPerWarReceived < 9 ? 'below market ~$9M ✓' : 'above market ~$9M'} tone={dollarPerWarReceived < 9 ? 'pos' : 'neg'} />}
                  {receivedArbTotal > 0 && <Stat label="3yr arb cost (in)" value={fmtMoney(receivedArbTotal)} sub={sentArbTotal > 0 ? `vs ${fmtMoney(sentArbTotal)} out` : 'proj. controlled cost'} tone={receivedArbTotal < sentArbTotal || sentArbTotal === 0 ? 'pos' : 'neutral'} />}
                </div>
                <div className="w-full pt-1 md:w-[420px]">
                  <PosteriorViolin
                    mean={verdict.surplusMean}
                    sd={verdict.surplusSd}
                    min={Math.min(verdict.surplusLo, -3)}
                    max={Math.max(verdict.surplusHi, 3)}
                    accent={verdict.reasoningTone}
                    unit=" WAR surplus"
                    width={420}
                    height={70}
                  />
                </div>
              </div>

              {/* Player comparison */}
              {(sendingPlayers.length > 0 || receivingPlayers.length > 0) && (
                <div className="border-t border-ink-700 px-5 pb-5 pt-4">
                  <TradeComparison
                    sendingPlayers={sendingPlayers}
                    receivingPlayers={receivingPlayers}
                    yourBref={yourBref}
                    partnerBref={partnerBref}
                    verdict={verdict}
                  />
                </div>
              )}
            </>
          )
        })() : (
          <div className="flex items-center gap-3 p-5 text-[13px] text-ink-300">
            <BadgePlus className="h-4 w-4 text-accent-400" />
            Add a player to either basket below to begin. The verdict updates live as you build.
          </div>
        )}
      </motion.div>

      {/* AI Reasoning bar */}
      <div className="card mb-6 flex flex-wrap items-center justify-between gap-3 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400">
            <Brain className="h-4 w-4" strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">AI Reasoning</div>
            <div className="text-[13px] text-ink-200">
              {override
                ? <span>Loaded analysis from Claude Code · saved {new Date(override.savedAt).toLocaleString()}.</span>
                : 'Get a structured analysis: copy the prompt, paste into Claude Code chat, paste JSON back.'}
            </div>
          </div>
        </div>
        <button
          onClick={() => setDrawerOpen(true)}
          disabled={!verdict}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-500"
        >
          <Terminal className="h-3.5 w-3.5" /> Reason with Claude Code
        </button>
      </div>

      {override?.reasoning ? (
        <div className="card mb-6 p-5">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Claude&apos;s headline</div>
          <div className="text-[15px] font-semibold leading-snug text-ink-100">{override.reasoning.headline}</div>
          <div className="mt-4 grid gap-4 md:grid-cols-[1fr_280px]">
            <div className="space-y-3 text-[13px] leading-relaxed text-ink-200">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Thesis</div>
                <p className="mt-1">{override.reasoning.thesis}</p>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Key drivers</div>
                <ul className="mt-1 space-y-2">
                  {override.reasoning.keyDrivers.map((d, i) => (
                    <li key={i} className="rounded-md border border-ink-700 bg-ink-800/40 p-2.5">
                      <div className="flex items-center gap-2">
                        {d.chip ? <span className="chip chip-accent mono">{d.chip}</span> : null}
                        <span className="text-[12.5px] font-semibold text-ink-100">{d.title}</span>
                      </div>
                      <div className="mt-1 text-[12px] text-ink-300">{d.body}</div>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Recommendation</div>
                <p className="mt-1 font-semibold text-ink-100">{override.reasoning.recommendation}</p>
              </div>
            </div>
            <div className="space-y-3 border-l border-ink-700 pl-4">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Watch-outs</div>
                <ul className="mt-1 space-y-2 text-[11px]">
                  {override.reasoning.watchOuts.map((w, i) => (
                    <li key={i} className="rounded-md bg-negative-500/[0.06] p-2">
                      <div className="font-semibold text-ink-100">{w.title}</div>
                      <div className="mt-0.5 text-ink-300">{w.body}</div>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Grounding</div>
                <ul className="mt-1 space-y-2 text-[11px]">
                  {override.reasoning.citations.map((c, i) => (
                    <li key={i} className="rounded-md border border-ink-700 bg-ink-800/60 p-2">
                      <div className="mono font-semibold text-accent-300">[{i + 1}] {c.label}</div>
                      <div className="mt-0.5 text-ink-300">{c.detail}</div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Three-column workshop */}
      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Section eyebrow={`${yourBref} sends`} title="Your roster" hint={`Click any player to add to '${yourBref} sends'`}>
          <div className="grid grid-rows-[1fr_180px] gap-3" style={{ height: 'calc(100vh - 320px)', minHeight: 540 }}>
            <PlayerPicker
              team={yourBref}
              onPickTeam={(b) => useIdentityStore.getState().setActiveTeam(b)}
              onAdd={addToSent}
              selectedIds={selectedAllIds}
              title={`${yourBref} 40-man`}
              hint="Filter by position / status; sorted by last-season WAR."
            />
            <BasketCard title={`${yourBref} sends`} team={yourTeam} players={sendingPlayers} onRemove={removeSent} emptyHint="Pick players from your roster above to offer." />
          </div>
        </Section>

        <Section eyebrow={`${yourBref} receives`} title={`Partner: ${partnerTeam.name}`} hint="Pick or search any of the other 29 clubs">
          <div className="grid grid-rows-[1fr_180px] gap-3" style={{ height: 'calc(100vh - 320px)', minHeight: 540 }}>
            <PlayerPicker
              team={partnerBref}
              onPickTeam={(b) => setPartnerBref(b)}
              onAdd={addToReceived}
              selectedIds={selectedAllIds}
              title="Trade-partner roster"
              hint="Pick from any of the other 29 clubs."
            />
            <BasketCard title={`${yourBref} receives`} team={partnerTeam} players={receivingPlayers} onRemove={removeReceived} emptyHint="Pick targets from the partner roster above." />
          </div>
        </Section>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-400">
        <span className="mono">
          Live data · 40-man rosters · {roster.player_count} active players · last sync {new Date(roster.refreshed_at).toLocaleString()} · refresh in header
        </span>
        <span className="mono">
          Synthetic posterior · v1 dev-signature multipliers · context features pre-V2 model
        </span>
      </div>

      {/* Reasoning drawer (inline lightweight version) */}
      <AnimatePresence>
        {drawerOpen && verdict && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} onClick={() => setDrawerOpen(false)} />
            <motion.aside
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', stiffness: 300, damping: 32 }}
              className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-ink-700 bg-ink-900"
            >
              <header className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400"><Terminal className="h-4 w-4" /></div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Reason with Claude Code</div>
                    <div className="text-[14px] font-semibold text-ink-100">{yourBref} ↔ {partnerBref} · {sendingPlayers.length}-for-{receivingPlayers.length} hypothetical</div>
                  </div>
                </div>
                <button onClick={() => setDrawerOpen(false)} className="rounded-md p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100"><X className="h-4 w-4" /></button>
              </header>
              <div className="flex-1 overflow-y-auto p-5">
                <section className="mb-5">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 1 · Generated prompt</div>
                      <div className="text-[12px] text-ink-300">Bundles trade structure, model snapshot, and ADRs.</div>
                    </div>
                    <button onClick={copyPrompt} className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 hover:bg-accent-400">
                      {copied ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? 'Copied' : 'Copy prompt'}
                    </button>
                  </div>
                  <pre className="max-h-64 overflow-y-auto rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[11px] leading-relaxed text-ink-300 mono whitespace-pre-wrap">{prompt}</pre>
                </section>
                <section className="mb-5 rounded-md border border-ink-700 bg-ink-800/50 p-4">
                  <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400"><Sparkles className="h-3 w-3" /> Step 2 · In Claude Code</div>
                  <ol className="ml-4 list-decimal space-y-1 text-[12px] text-ink-200 marker:text-ink-500">
                    <li>Paste the prompt into Claude Code chat</li>
                    <li>Claude returns a single fenced <code className="mono rounded bg-ink-700 px-1 text-[10.5px]">```json</code> block</li>
                    <li>Copy that block (fences OK) and paste below</li>
                  </ol>
                </section>
                <section>
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 3 · Paste response</div>
                      <div className="text-[12px] text-ink-300">JSON validates against AiReasoning schema.</div>
                    </div>
                    {override && (
                      <button onClick={() => { useReasoningStore.getState().clear(hypoId); setPasteText(''); setPasteError(null); setPasteOk(false) }} className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1 text-[11px] text-ink-300 hover:border-negative-500/50 hover:text-negative-500">
                        <RotateCcw className="h-3 w-3" /> Clear saved
                      </button>
                    )}
                  </div>
                  <textarea
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                    placeholder="```json&#10;{ ... }&#10;```"
                    rows={10}
                    className="mono w-full rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[12px] leading-relaxed text-ink-200 placeholder:text-ink-500 focus:border-accent-500/50 focus:outline-none"
                    spellCheck={false}
                  />
                  {pasteError && (
                    <div className="mt-2 flex items-start gap-2 rounded-md border border-negative-500/40 bg-negative-500/10 px-3 py-2 text-[12px] text-negative-500">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{pasteError}</span>
                    </div>
                  )}
                  {pasteOk && (
                    <div className="mt-2 flex items-center gap-2 rounded-md border border-positive-500/40 bg-positive-500/10 px-3 py-2 text-[12px] text-positive-500">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Applied. Reasoning panel updated.
                    </div>
                  )}
                  <div className="mt-3 flex items-center justify-end gap-2">
                    <button onClick={() => setDrawerOpen(false)} className="rounded-md border border-ink-700 px-3 py-1.5 text-[12px] text-ink-300 hover:border-ink-500 hover:text-ink-100">Done</button>
                    <button onClick={applyPaste} disabled={!pasteText.trim()} className="rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-500">Parse &amp; apply</button>
                  </div>
                </section>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </main>
  )
}
