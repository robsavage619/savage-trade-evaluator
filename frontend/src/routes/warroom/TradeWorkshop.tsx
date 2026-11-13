import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowLeftRight, Trash2, X, BadgePlus, Radio } from 'lucide-react'
import { PlayerPicker, BasketCard } from '../../components/PlayerPicker'
import { Stat } from '../../components/Section'
import { ForecastBlindSpots } from '../../components/ForecastBlindSpots'
import { ForecastFootnote } from '../../components/ForecastFootnote'
import { fvToWar } from '../../lib/hypothetical'
import { LEAN_LABEL, comparePackages, fmtWar, leanOf } from '../../lib/structuralData'
import { dollarsAsOf } from '../../lib/contractDollars'
import { packageFacts, salarySource } from '../../lib/tradeFacts'
import type { ProspectEntry, VerdictContext } from '../../lib/hypothetical'
import type { CurrentPlayer } from '../../data/players'
import type { ScenarioCard } from '../../data/warroom/types'
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
        <span className="font-mono text-[8.5px] uppercase tracking-[0.08em] text-ink-600">Season W Impact</span>
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

const GRADE_COLOR: Record<string, string> = {
  A: 'text-positive-400 border-positive-400/40',
  B: 'text-accent-300 border-accent-400/40',
  C: 'text-yellow-400 border-yellow-400/40',
  D: 'text-negative-400 border-negative-400/40',
}

function ScenarioCardRow({ sc }: { sc: ScenarioCard }) {
  const wd = sc.warDelta
  const grade = wd?.coverageGrade ?? null
  const gradeClass = grade ? GRADE_COLOR[grade] ?? '' : ''
  const pPos = wd?.pPositive != null ? Math.round(wd.pPositive * 100) : null
  const sparseLow = grade === 'C' || grade === 'D'
  return (
    <div className="rounded border border-ink-700/50 bg-ink-800/30 px-3 py-2">
      <div className="mb-1 flex items-center gap-2">
        <span className="font-mono text-[9px] text-ink-500">Season {sc.tradeSeason}</span>
        {grade && (
          <span className={`rounded border px-1.5 py-0.5 font-mono text-[8px] font-bold ${gradeClass}`}>
            {grade}
          </span>
        )}
        {sparseLow && (
          <span className="font-mono text-[8px] text-yellow-500/80">extrapolating from training means</span>
        )}
      </div>
      {wd && (
        <div className="flex flex-wrap gap-4">
          <div className="font-mono text-[10px]">
            <span className="text-ink-400">WAR Δ </span>
            <span className={wd.mean != null && wd.mean >= 0 ? 'text-positive-400' : 'text-negative-400'}>
              {wd.mean != null ? (wd.mean >= 0 ? '+' : '') + wd.mean.toFixed(2) : '—'}
            </span>
            {wd.p5 != null && wd.p95 != null && (
              <span className="text-ink-500"> [{wd.p5.toFixed(1)}, {wd.p95.toFixed(1)}]</span>
            )}
          </div>
          {pPos != null && (
            <div className="font-mono text-[10px] text-ink-400">
              P(+) <span className="text-ink-200">{pPos}%</span>
            </div>
          )}
        </div>
      )}
      {wd?.attribution && wd.attribution.length > 0 && (() => {
        const maxAbs = Math.max(...wd.attribution.map(a => Math.abs(a.contribution)), 0.001)
        return (
          <div className="mt-2 space-y-1">
            {wd.attribution.map((a, i) => {
              const pct = Math.abs(a.contribution) / maxAbs * 100
              const pos = a.contribution >= 0
              return (
                <div key={i} className="flex items-center gap-2">
                  <div className="w-28 shrink-0 font-mono text-[8px] text-ink-500 truncate" title={a.feature.replace(/_/g, ' ')}>
                    {a.feature.replace(/_/g, ' ')}
                    {!a.observed && <span className="ml-0.5 text-ink-700">*</span>}
                  </div>
                  <div className="flex flex-1 items-center">
                    {/* negative half */}
                    <div className="flex flex-1 justify-end">
                      {!pos && (
                        <div
                          className="h-1.5 rounded-l-sm bg-negative-400/60"
                          style={{ width: `${pct}%` }}
                        />
                      )}
                    </div>
                    {/* centre line */}
                    <div className="mx-px h-3 w-px bg-ink-700 shrink-0" />
                    {/* positive half */}
                    <div className="flex flex-1">
                      {pos && (
                        <div
                          className="h-1.5 rounded-r-sm bg-positive-400/60"
                          style={{ width: `${pct}%` }}
                        />
                      )}
                    </div>
                  </div>
                  <div className={`w-12 shrink-0 text-right font-mono text-[8px] ${pos ? 'text-positive-400/70' : 'text-negative-400/70'}`}>
                    {pos ? '+' : ''}{a.contribution.toFixed(3)}
                  </div>
                </div>
              )
            })}
          </div>
        )
      })()}
    </div>
  )
}

export function TradeWorkshop({ yourBref, partnerBref, verdictCtx, scenarios = [] }: {
  yourBref: string
  partnerBref: string
  verdictCtx: VerdictContext
  scenarios?: ScenarioCard[]
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

  const forecast = useMemo(
    () => sendingPlayers.length + receivingPlayers.length > 0
      ? comparePackages(receivingPlayers.map(p => p.mlb_player_id), sendingPlayers.map(p => p.mlb_player_id))
      : null,
    [sendingPlayers, receivingPlayers],
  )

  const factsIn = useMemo(() => packageFacts(receivingPlayers), [receivingPlayers])
  const factsOut = useMemo(() => packageFacts(sendingPlayers), [sendingPlayers])
  const prospectWar = (ps: ProspectEntry[]) => ps.reduce((a, q) => a + fvToWar(q.fvGrade), 0)

  if (!yourTeam || !partnerTeam) return null

  const { currentW = 0, currentL = 0, gamesBack = 0, playoffProb = 0.4 } = verdictCtx as {
    currentW?: number; currentL?: number; gamesBack?: number; playoffProb?: number
  }
  const costIn = factsIn.yr1Cost
  const costOut = factsOut.yr1Cost
  const salaryDelta = costIn - costOut
  const net = forecast?.net
  const lean = net ? leanOf(net) : 'even'
  const leanLabel = LEAN_LABEL[lean]
  const recBorder = lean === 'receive'
    ? 'border-positive-500/30 bg-positive-500/5'
    : lean === 'send'
    ? 'border-negative-500/30 bg-negative-500/5'
    : 'border-ink-700 bg-ink-800/40'
  const netColor = (net?.mean ?? 0) >= 0 ? 'text-positive-400' : 'text-negative-400'
  const pct = (v: number) => `${Math.round(v * 100)}%`
  const missing = (forecast?.received.missing ?? 0) + (forecast?.sent.missing ?? 0)
  const band = (f: { mean: number; p5: number; p95: number }) => ({
    value: fmtWar(f.mean),
    sub: `90% ${fmtWar(f.p5)} to ${fmtWar(f.p95)}`,
  })

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
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-300">
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

      {/* Forecast */}
      {forecast && net ? (
        <div className={`mb-4 rounded-lg border p-4 ${recBorder}`}>
          <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-500">
            Captured-WAR forecast · this season through T+5
          </div>
          <div className="mb-3 flex items-end gap-4">
            <div>
              <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-500">Net WAR for {yourBref}</div>
              <div className={`font-mono text-[40px] font-black leading-none tabular ${netColor}`}>
                {net.mean >= 0 ? '+' : '−'}
                <AnimatedNumber end={Math.abs(net.mean)} decimals={1} suffix=" WAR" />
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-ink-400">
                90% {fmtWar(net.p5)} to {fmtWar(net.p95)} ·
                P(receive side ahead) <span className={netColor}>{pct(net.pPositive)}</span> ·
                {' '}{leanLabel}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-4 border-t border-ink-700/40 pt-2.5">
            <Stat label="WAR in" {...band(forecast.received)} tone="pos" />
            <Stat label="WAR out" {...band(forecast.sent)} tone="neg" />
            <Stat label={`Salary Δ (${dollarsAsOf.season})`} value={`${salaryDelta <= 0 ? '−' : '+'}${fmtMoney(Math.abs(salaryDelta))}`} sub={`In ${fmtMoney(costIn)} · Out ${fmtMoney(costOut)} · ${salarySource(factsIn, factsOut)}`} tone={salaryDelta <= 0 ? 'pos' : 'neg'} />
            {factsIn.controlledCost3yr > 0 && (
              <Stat label="Arb path (in)" value={fmtMoney(factsIn.controlledCost3yr)} sub={factsOut.controlledCost3yr > 0 ? `vs ${fmtMoney(factsOut.controlledCost3yr)} out` : '3yr proj.'} tone="neutral" />
            )}
            {factsIn.extensionEst > 0 && (
              <Stat label="Extension est (in)" value={fmtMoney(factsIn.extensionEst)} sub="realistic lock-up cost · agent leverage" tone="neg" />
            )}
            {(receivedProspects.length > 0 || sentProspects.length > 0) && (
              <Stat
                label="Prospects"
                value={`+${prospectWar(receivedProspects).toFixed(1)} / −${prospectWar(sentProspects).toFixed(1)}`}
                sub="FV table · not in the forecast · unvalidated"
                tone="neutral"
              />
            )}
          </div>
          <WinImpact
            warDelta={forecast.received.ratePerSeason - forecast.sent.ratePerSeason}
            currentW={currentW}
            currentL={currentL}
            gamesBack={gamesBack}
            playoffProb={playoffProb}
          />
          <ForecastBlindSpots players={[...receivingPlayers, ...sendingPlayers]} className="mt-2" />
          <ForecastFootnote missing={missing} className="mt-2 rounded border border-ink-700/50 bg-ink-800/40 px-2.5 py-1.5" />
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-dashed border-ink-700 px-3 py-2.5 text-[11px] text-ink-400">
          <BadgePlus className="h-3.5 w-3.5 text-accent-400/60" />
          Add players to a basket to see the forecast. Prospects are not in the validated model.
        </div>
      )}

      {/* Baskets */}
      <div className="mb-3 grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.1em] text-negative-400">
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
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.1em] text-positive-400">
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

      {/* Historical model scenarios */}
      {(() => {
        const scored = scenarios.filter(sc => sc.warDelta != null)
        if (scored.length > 0) {
          return (
            <div className="mt-3">
              <div className="mb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.08em] text-ink-500">
                Historical model scenarios · v{scored[0].modelVersion}
              </div>
              <div className="flex flex-col gap-2">
                {scored.map(sc => (
                  <ScenarioCardRow key={sc.tradeEventId} sc={sc} />
                ))}
              </div>
            </div>
          )
        }
        if (scenarios.length > 0) {
          return (
            <div className="mt-3 rounded border border-dashed border-ink-700 px-3 py-2.5 font-mono text-[10px] text-ink-500">
              No scored scenarios on file for this team — run{' '}
              <code className="text-ink-400">ste export-warroom --with-scenarios</code> to populate.
            </div>
          )
        }
        return null
      })()}
    </motion.div>
  )
}
