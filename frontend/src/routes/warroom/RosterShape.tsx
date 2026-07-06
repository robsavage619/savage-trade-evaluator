import { useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
} from 'recharts'
import type { HoleEntry, WindowPosture } from '../../data/warroom/types'
import { SEVERITY_COLOR, HOLE_SCORE_CITE, SURPLUS_WAR_CITE } from './shared'
import { Cite } from './primitives'

// ── position radar ────────────────────────────────────────────────────────────

export function PositionRadar({ holes, surpluses, posture }: { holes: HoleEntry[]; surpluses: HoleEntry[]; posture: WindowPosture }) {
  const data = useMemo(() => {
    const allPositions = [...new Set([...holes, ...surpluses].map(h => h.position))]
    return allPositions.map(pos => {
      const hole = holes.find(h => h.position === pos)
      const surplus = surpluses.find(h => h.position === pos)
      // 0 = critical gap, 50 = replacement level, 100 = major surplus
      const score = hole
        ? Math.max(0, 50 - (hole.holeScore / hole.replacementBaseline) * 50)
        : surplus
        ? Math.min(100, 50 + ((surplus.surplus ?? 0) / surplus.replacementBaseline) * 50)
        : 50
      return { position: pos, value: Math.round(score) }
    })
  }, [holes, surpluses])

  if (data.length < 3) return null

  const radarColor = posture === 'buy' ? '#3ddc97' : posture === 'sell' ? '#ff5d73' : '#ff8a3d'

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Position Shape</span>
        <Cite cite={{ label: 'Position Shape Radar', detail: '0 = critical gap (well below replacement) · 50 = replacement level · 100 = tradeable surplus. Shape shows where your roster over- and under-produces relative to league baseline.' }} />
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <RadarChart data={data} margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
          <PolarGrid stroke="#1a2238" />
          <PolarAngleAxis
            dataKey="position"
            tick={{ fill: '#8a96c0', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          />
          <Radar
            dataKey="value"
            stroke={radarColor}
            fill={radarColor}
            fillOpacity={0.15}
            strokeWidth={1.5}
            dot={{ r: 2.5, fill: radarColor, strokeWidth: 0 }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── holes board ──────────────────────────────────────────────────────────────

export function HolesBoard({ holes, surpluses }: { holes: HoleEntry[]; surpluses: HoleEntry[] }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      {holes.length > 0 && (
        <div className="mb-4">
          <div className="mb-2.5 flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-negative-400">▼ Needs</span>
            <Cite cite={HOLE_SCORE_CITE} />
          </div>
          <div className="space-y-2">
            {holes.map((h, i) => (
              <motion.div
                key={h.position}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center gap-3"
                style={{ borderLeft: `3px solid ${SEVERITY_COLOR[h.severity]}` }}
              >
                <span className="font-mono w-8 shrink-0 pl-2.5 text-[12px] font-bold text-ink-100">{h.position}</span>
                <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-ink-800">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (h.holeScore / h.replacementBaseline) * 100)}%` }}
                    transition={{ duration: 0.8, delay: i * 0.05, ease: 'easeOut' }}
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{ background: SEVERITY_COLOR[h.severity], boxShadow: `0 0 8px ${SEVERITY_COLOR[h.severity]}60` }}
                  />
                </div>
                <div className="shrink-0 flex items-center gap-1.5">
                  <span className="font-mono text-[15px] font-black leading-none tabular text-negative-400">
                    −{h.holeScore.toFixed(1)}
                  </span>
                  {h.severity === 'critical' && (
                    <span className="rounded bg-negative-500/15 px-1 py-px font-mono text-[8px] font-bold uppercase tracking-wider text-negative-400">CRIT</span>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}
      {surpluses.length > 0 && (
        <div>
          <div className="mb-2.5 flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-positive-400">▲ Tradeable surplus</span>
            <Cite cite={SURPLUS_WAR_CITE} />
          </div>
          <div className="space-y-2">
            {surpluses.map((h, i) => (
              <motion.div
                key={h.position}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 + 0.15 }}
                className="flex items-center gap-3 border-l-[3px] border-positive-500/50"
              >
                <span className="font-mono w-8 shrink-0 pl-2.5 text-[12px] font-bold text-ink-100">{h.position}</span>
                <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-ink-800">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, ((h.surplus ?? 0) / h.replacementBaseline) * 100)}%` }}
                    transition={{ duration: 0.8, delay: i * 0.05 + 0.15, ease: 'easeOut' }}
                    className="absolute inset-y-0 left-0 rounded-full bg-positive-500/70"
                    style={{ boxShadow: '0 0 8px rgba(61,220,151,0.4)' }}
                  />
                </div>
                <span className="font-mono shrink-0 text-[15px] font-black leading-none tabular text-positive-400">
                  +{(h.surplus ?? 0).toFixed(1)}
                </span>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
