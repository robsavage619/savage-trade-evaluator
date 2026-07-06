import { useMemo } from 'react'
import { motion } from 'framer-motion'
import type { HoleEntry } from '../../data/warroom/types'
import type { DealCandidate } from '../../lib/dealsEngine'
import type { BuyLowCandidate } from '../../lib/buyLowEngine'
import { TeamLogo } from '../../components/TeamLogo'
import { fmtMoney } from '../../lib/format'
import { POSTURE, SEVERITY_WEIGHT, SURPLUS_WAR_CITE } from './shared'
import { Cite } from './primitives'

// ── position market scan ──────────────────────────────────────────────────────

export function PositionMarketScan({ candidates, holes }: { candidates: BuyLowCandidate[]; holes: HoleEntry[] }) {
  // Group candidates by their primary hole position
  const byHole = useMemo(() => {
    const map: Record<string, BuyLowCandidate[]> = {}
    for (const c of candidates) {
      const primary = c.holesFilled
        .sort((a, b) => (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0))[0]
      if (!primary) continue
      const pos = primary.position
      if (!map[pos]) map[pos] = []
      map[pos].push(c)
    }
    return map
  }, [candidates])

  // Order by hole severity (critical first)
  const orderedHoles = useMemo(() =>
    [...holes].sort((a, b) => (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0)),
    [holes]
  )

  if (candidates.length === 0) return (
    <div className="py-4 text-center font-mono text-[11px] text-ink-500">No buy-low targets found for your holes.</div>
  )

  return (
    <div className="space-y-3">
      {orderedHoles.map(hole => {
        const targets = byHole[hole.position]
        if (!targets || targets.length === 0) return null
        const severityColor = hole.severity === 'critical' ? 'text-negative-400 border-negative-500/30' : 'text-accent-300 border-accent-500/30'
        return (
          <div key={hole.position}>
            <div className={`mb-1.5 flex items-center gap-2 border-b pb-1 ${severityColor}`}>
              <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em]">{hole.position}</span>
              {hole.severity === 'critical' && <span className="font-mono text-[8px] font-bold text-negative-500">CRITICAL NEED</span>}
              <span className="ml-auto font-mono text-[8.5px] text-ink-600">{targets.length} targets</span>
            </div>
            <div className="space-y-1">
              {targets.slice(0, 3).map(c => {
                const postureCfg = POSTURE[c.sourcePosture]
                return (
                  <div
                    key={c.player.mlb_player_id}
                    className="flex items-center gap-2.5 rounded border border-ink-700 bg-ink-900/40 px-2.5 py-1.5"
                  >
                    <TeamLogo team={c.sourceTeam.bref} size={18} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate font-mono text-[11px] font-semibold text-ink-100">{c.player.name}</span>
                        <span className={`font-mono text-[8px] font-bold ${postureCfg.color}`}>{c.sourceTeam.bref}</span>
                      </div>
                      <div className="font-mono text-[9.5px] text-ink-400">
                        {c.player.age ?? '?'}y · +{c.adjWar.toFixed(1)} WAR · {fmtMoney(c.yr1Cost)}/yr · {c.yearsControlled}yr ctrl
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className={`font-mono text-[14px] font-black leading-none ${c.surplusWar > 4 ? 'text-positive-400' : c.surplusWar > 2 ? 'text-accent-400' : 'text-ink-300'}`}>
                        +{c.surplusWar.toFixed(1)}
                      </div>
                      <div className="flex items-center justify-end gap-0.5 mt-0.5">
                        <span className="font-mono text-[8px] text-ink-600">sWAR</span>
                        <Cite cite={SURPLUS_WAR_CITE} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── deals that clear ──────────────────────────────────────────────────────────

export function DealsThatClear({ deals, onSelect }: { deals: DealCandidate[]; onSelect: (bref: string) => void }) {
  if (deals.length === 0) return (
    <div className="py-4 text-center font-mono text-[11px] text-ink-500">No mutual deals found yet.</div>
  )
  return (
    <div className="space-y-2">
      {deals.map((d, i) => {
        const cfg = POSTURE[d.partnerPosture]
        return (
          <motion.button
            key={d.partnerBref}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ x: 2 }}
            onClick={() => onSelect(d.partnerBref)}
            className="w-full rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2.5 text-left transition-colors hover:border-ink-600 hover:bg-ink-800/60"
          >
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <TeamLogo team={d.partnerBref} size={20} />
                <span className="font-mono text-[12px] font-bold text-ink-100">{d.partnerBref}</span>
                <span className={`font-mono text-[9px] font-semibold ${cfg.color}`}>{d.partnerPosture.toUpperCase()}</span>
                <span className="font-mono text-[10px] text-ink-400">{d.partnerWL}</span>
              </div>
              <div className="font-mono text-[10px] text-ink-400">
                hdroom <span className={d.partnerHeadroom > 0 ? 'text-positive-400' : 'text-negative-400'}>{fmtMoney(d.partnerHeadroom)}</span>
              </div>
            </div>
            <div className="flex gap-4 text-[10px]">
              <div>
                <span className="font-mono text-[8px] uppercase tracking-wider text-positive-500">They give</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {d.theyFill.map(h => (
                    <span key={h.position} className={`rounded border px-1 py-px font-mono text-[9px] ${h.severity === 'critical' ? 'border-negative-500/40 text-negative-400' : 'border-ink-600 text-ink-300'}`}>
                      {h.position}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <span className="font-mono text-[8px] uppercase tracking-wider text-accent-500">You give</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {d.youFill.map(h => (
                    <span key={h.position} className="rounded border border-ink-600 px-1 py-px font-mono text-[9px] text-ink-300">
                      {h.position}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </motion.button>
        )
      })}
    </div>
  )
}
