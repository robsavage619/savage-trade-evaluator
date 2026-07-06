import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowLeftRight, Trash2, X, BadgePlus, Radio } from 'lucide-react'
import { PlayerPicker, BasketCard } from '../../components/PlayerPicker'
import { Stat } from '../../components/Section'
import { forecastArb, isControlled } from '../../lib/arbForecast'
import { computeVerdict, fvToWar } from '../../lib/hypothetical'
import type { ProspectEntry, VerdictContext } from '../../lib/hypothetical'
import type { CurrentPlayer } from '../../data/players'
import { useTeamsByBref } from '../../lib/rosterStore'
import { fmtMoney } from '../../lib/format'
import { AnimatedNumber } from './primitives'

// ── prospect adder ─────────────────────────────────────────────────────────────

const FV_OPTIONS = [80, 70, 60, 55, 50, 45, 40] as const

function ProspectAdder({ onAdd }: { onAdd: (p: ProspectEntry) => void }) {
  const [name, setName] = useState('')
  const [fv, setFv] = useState<ProspectEntry['fvGrade']>(50)
  return (
    <div className="mt-1.5 flex gap-1">
      <input
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && name.trim()) { onAdd({ name: name.trim(), fvGrade: fv }); setName('') } }}
        placeholder="Prospect name…"
        className="min-w-0 flex-1 rounded border border-ink-700 bg-ink-800/60 px-2 py-1 text-[11px] text-ink-100 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
      />
      <select
        value={fv}
        onChange={e => setFv(Number(e.target.value) as ProspectEntry['fvGrade'])}
        className="rounded border border-ink-700 bg-ink-800 px-1.5 py-1 text-[11px] text-ink-200 focus:outline-none"
      >
        {FV_OPTIONS.map(v => <option key={v} value={v}>{v} FV (~{fvToWar(v).toFixed(1)} WAR)</option>)}
      </select>
      <button
        onClick={() => { if (name.trim()) { onAdd({ name: name.trim(), fvGrade: fv }); setName('') } }}
        className="rounded border border-accent-500/40 bg-accent-500/10 px-2 py-1 font-mono text-[10px] text-accent-300 transition-colors hover:bg-accent-500/20"
      >
        +
      </button>
    </div>
  )
}

// ── win impact strip ─────────────────────────────────────────────────────────

function WinImpact({
  warDelta, currentW, currentL, gamesBack, playoffProb,
}: {
  warDelta: number; currentW: number; currentL: number; gamesBack: number; playoffProb: number
}) {
  const gamesPlayed = currentW + currentL
  const gamesRemaining = Math.max(1, 162 - gamesPlayed)
  // Marginal wins this season from the WAR delta (prorated to games remaining)
  const marginalWins = warDelta * (gamesRemaining / 162)
  const newW = currentW + marginalWins
  const newGB = Math.max(0, gamesBack - marginalWins)
  // Use the same logistic formula from computePlayoffProb
  const probBefore = playoffProb
  const probAfter = Math.max(0.02, Math.min(0.97, 1 / (1 + Math.exp(-((newW / (newW + currentL) - 0.5) * 12 - newGB * 0.12 - 0.25)))))
  const delta = probAfter - probBefore
  const sign = marginalWins >= 0 ? '+' : ''
  const deltaSign = delta >= 0 ? '+' : ''
  const color = delta > 0.04 ? 'text-positive-400' : delta > 0 ? 'text-positive-500' : delta < -0.04 ? 'text-negative-400' : 'text-ink-400'

  return (
    <div className="mt-3 flex items-center gap-4 rounded-lg border border-ink-700/50 bg-ink-900/40 px-3 py-2">
      <div className="flex flex-col">
        <span className="font-mono text-[8.5px] uppercase tracking-[0.2em] text-ink-600">Season W Impact</span>
        <span className={`font-mono text-[18px] font-black leading-none tabular ${marginalWins >= 0 ? 'text-positive-400' : 'text-negative-400'}`}>
          {sign}{marginalWins.toFixed(1)}W
        </span>
        <span className="font-mono text-[8.5px] text-ink-600">{gamesRemaining} G remaining</span>
      </div>
      <div className="h-8 w-px bg-ink-700" />
      <div className="flex items-center gap-2">
        <div className="flex flex-col items-center">
          <span className="font-mono text-[8.5px] text-ink-600">Before</span>
          <span className="font-mono text-[16px] font-bold text-ink-400">{Math.round(probBefore * 100)}%</span>
        </div>
        <span className="font-mono text-[10px] text-ink-600">→</span>
        <div className="flex flex-col items-center">
          <span className="font-mono text-[8.5px] text-ink-600">After</span>
          <span className={`font-mono text-[16px] font-bold ${color}`}>{Math.round(probAfter * 100)}%</span>
        </div>
        <span className={`font-mono text-[11px] font-semibold ${color}`}>({deltaSign}{Math.round(delta * 100)}pp)</span>
      </div>
      <div className="ml-auto font-mono text-[8.5px] text-ink-600">P(playoff)</div>
    </div>
  )
}

// ── trade workshop ─────────────────────────────────────────────────────────────

export function TradeWorkshop({ yourBref, partnerBref, verdictCtx }: {
  yourBref: string
  partnerBref: string
  verdictCtx: VerdictContext
}) {
  const teamsByBref = useTeamsByBref()
  const yourTeam = teamsByBref[yourBref]
  const partnerTeam = teamsByBref[partnerBref]
  const [sentIds, setSentIds] = useState<number[]>([])
  const [receivedIds, setReceivedIds] = useState<number[]>([])
  const [sentProspects, setSentProspects] = useState<ProspectEntry[]>([])
  const [receivedProspects, setReceivedProspects] = useState<ProspectEntry[]>([])

  useEffect(() => {
    setSentIds([]); setReceivedIds([])
    setSentProspects([]); setReceivedProspects([])
  }, [partnerBref])

  const sendingPlayers = useMemo(
    () => sentIds.map(id => yourTeam?.players.find(p => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [sentIds, yourTeam],
  )
  const receivingPlayers = useMemo(
    () => receivedIds.map(id => partnerTeam?.players.find(p => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [receivedIds, partnerTeam],
  )

  const verdict = useMemo(
    () => yourTeam && partnerTeam
      ? computeVerdict(
          {
            sending: { team: yourTeam, players: sendingPlayers, prospects: sentProspects },
            receiving: { team: partnerTeam, players: receivingPlayers, prospects: receivedProspects },
          },
          verdictCtx,
        )
      : null,
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers, sentProspects, receivedProspects, verdictCtx],
  )

  const receivedArbTotal = useMemo(() =>
    receivingPlayers.reduce((acc, p) => {
      const a = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
      return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
    }, 0), [receivingPlayers],
  )
  const sentArbTotal = useMemo(() =>
    sendingPlayers.reduce((acc, p) => {
      const a = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
      return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
    }, 0), [sendingPlayers],
  )

  if (!yourTeam || !partnerTeam) return null

  const { currentW = 0, currentL = 0, gamesBack = 0, playoffProb = 0.4 } = verdictCtx as {
    currentW?: number; currentL?: number; gamesBack?: number; playoffProb?: number
  }
  const salaryDelta = (verdict?.costReceived ?? 0) - (verdict?.costSent ?? 0)
  const rec = verdict?.recommendation
  const recBorder = rec === 'strong-buy' || rec === 'lean-buy'
    ? 'border-positive-500/30 bg-positive-500/5'
    : rec === 'strong-pass' || rec === 'lean-pass'
    ? 'border-negative-500/30 bg-negative-500/5'
    : 'border-ink-700 bg-ink-800/40'
  const dollarColor = (verdict?.netValueDollars ?? 0) >= 0 ? 'text-positive-400' : 'text-negative-400'

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 rounded-lg border border-ink-700 bg-ink-900/80 p-4"
      style={{ boxShadow: '0 0 40px rgba(0,0,0,0.4) inset' }}
    >
      {/* Header bar */}
      <div className="mb-4 flex items-center justify-between border-b border-ink-700 pb-3">
        <div className="flex items-center gap-2.5">
          <Radio className="h-3.5 w-3.5 text-accent-400" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-300">
            Trade Workshop
          </span>
          <span className="font-mono text-[10px] text-ink-400">
            {yourBref} <ArrowLeftRight className="inline h-2.5 w-2.5" /> {partnerBref}
          </span>
        </div>
        <button
          onClick={() => { setSentIds([]); setReceivedIds([]); setSentProspects([]); setReceivedProspects([]) }}
          className="flex items-center gap-1 font-mono text-[9px] text-ink-600 transition-colors hover:text-negative-400"
        >
          <Trash2 className="h-3 w-3" /> CLEAR
        </button>
      </div>

      {/* Verdict */}
      {verdict ? (
        <div className={`mb-4 rounded-lg border p-4 ${recBorder}`}>
          <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">
            GM Decision Signal
          </div>
          {/* Primary: single dollar value */}
          <div className="mb-3 flex items-end gap-4">
            <div>
              <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">Net surplus value</div>
              <div className={`font-mono text-[40px] font-black leading-none tabular ${dollarColor}`}>
                {(verdict.netValueDollars >= 0 ? '+' : '−')}
                <AnimatedNumber
                  end={Math.abs(verdict.netValueDollars) / 1_000_000}
                  decimals={1}
                  prefix="$"
                  suffix="M"
                />
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-ink-400">
                {verdict.surplusMean >= 0 ? '+' : ''}{verdict.surplusMean.toFixed(1)} WAR 3yr ·
                P(+) <span className={dollarColor}>{Math.round(verdict.pPositive * 100)}%</span> ·
                {' '}{verdict.recommendationLabel}
              </div>
            </div>
          </div>
          {/* Secondary decomposition */}
          <div className="flex flex-wrap gap-4 border-t border-ink-700/40 pt-2.5">
            <Stat label="WAR Δ (3yr)" value={`${(verdict.warReceived - verdict.warSent) >= 0 ? '+' : ''}${(verdict.warReceived - verdict.warSent).toFixed(1)}`} sub="aging + dev adjusted" tone={verdict.reasoningTone} />
            <Stat label="Salary Δ" value={`${salaryDelta <= 0 ? '−' : '+'}${fmtMoney(Math.abs(salaryDelta))}`} sub={`In ${fmtMoney(verdict.costReceived)} · Out ${fmtMoney(verdict.costSent)}`} tone={salaryDelta <= 0 ? 'pos' : 'neg'} />
            {receivedArbTotal > 0 && (
              <Stat label="Arb path (in)" value={fmtMoney(receivedArbTotal)} sub={sentArbTotal > 0 ? `vs ${fmtMoney(sentArbTotal)} out` : '3yr proj.'} tone="neutral" />
            )}
            {verdict.extensionEstReceived > 0 && (
              <Stat
                label="Extension est (in)"
                value={fmtMoney(verdict.extensionEstReceived)}
                sub="realistic lock-up cost · agent leverage"
                tone="neg"
              />
            )}
            {verdict.deadlinePremiumApplied && (
              <div className="flex flex-col gap-0.5">
                <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Deadline premium</div>
                <div className="font-mono text-[11px] font-bold text-accent-300">Applied</div>
                <div className="text-[10px] text-ink-500">playoff probability uplift included</div>
              </div>
            )}
          </div>
          {/* Win impact */}
          <WinImpact
            warDelta={verdict.warReceived - verdict.warSent}
            currentW={currentW}
            currentL={currentL}
            gamesBack={gamesBack}
            playoffProb={playoffProb}
          />
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-dashed border-ink-700 px-3 py-2.5 text-[11px] text-ink-400">
          <BadgePlus className="h-3.5 w-3.5 text-accent-400/60" />
          Add players to both baskets to activate the verdict.
        </div>
      )}

      {/* Baskets */}
      <div className="mb-3 grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-negative-400">
            ◀ {yourBref} sends
          </div>
          <BasketCard title={`${yourBref} sends`} team={yourTeam} players={sendingPlayers}
            onRemove={id => setSentIds(p => p.filter(x => x !== id))} emptyHint="Pick from your roster below." />
          {/* Prospect adder — sends side */}
          {sentProspects.length > 0 && (
            <div className="mt-1.5 space-y-1">
              {sentProspects.map((q, i) => (
                <div key={`${q.name}-${q.fvGrade}`} className="flex items-center justify-between rounded border border-ink-700 bg-ink-900/40 px-2 py-1 text-[11px]">
                  <span className="text-ink-200">{q.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[9px] text-accent-400">{q.fvGrade} FV</span>
                    <button onClick={() => setSentProspects(p => p.filter((_, j) => j !== i))} className="text-ink-600 hover:text-negative-400"><X className="h-3 w-3" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <ProspectAdder onAdd={p => setSentProspects(prev => [...prev, p])} />
        </div>
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-positive-400">
            ▶ {yourBref} receives
          </div>
          <BasketCard title={`${yourBref} receives`} team={partnerTeam} players={receivingPlayers}
            onRemove={id => setReceivedIds(p => p.filter(x => x !== id))} emptyHint="Pick from partner roster below." />
          {/* Prospect adder — receives side */}
          {receivedProspects.length > 0 && (
            <div className="mt-1.5 space-y-1">
              {receivedProspects.map((q, i) => (
                <div key={`${q.name}-${q.fvGrade}`} className="flex items-center justify-between rounded border border-ink-700 bg-ink-900/40 px-2 py-1 text-[11px]">
                  <span className="text-ink-200">{q.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[9px] text-accent-400">{q.fvGrade} FV</span>
                    <button onClick={() => setReceivedProspects(p => p.filter((_, j) => j !== i))} className="text-ink-600 hover:text-negative-400"><X className="h-3 w-3" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <ProspectAdder onAdd={p => setReceivedProspects(prev => [...prev, p])} />
        </div>
      </div>

      {/* Pickers */}
      <div className="grid gap-3 md:grid-cols-2">
        <PlayerPicker team={yourBref} onPickTeam={() => {}}
          onAdd={p => setSentIds(prev => prev.includes(p.mlb_player_id) ? prev : [...prev, p.mlb_player_id])}
          selectedIds={new Set(sentIds)} title={`${yourBref} roster`} hint={`Click → '${yourBref} sends'`} />
        <PlayerPicker team={partnerBref} onPickTeam={() => {}}
          onAdd={p => setReceivedIds(prev => prev.includes(p.mlb_player_id) ? prev : [...prev, p.mlb_player_id])}
          selectedIds={new Set(receivedIds)} title={`${partnerBref} roster`} hint={`Click → '${yourBref} receives'`} />
      </div>
    </motion.div>
  )
}
