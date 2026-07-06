import { motion } from 'framer-motion'
import type { WindowPosture } from '../../data/warroom/types'
import { POSTURE } from './shared'
import { Cite, PulseDot } from './primitives'

export function PostureBanner({ posture, rationale, playoffProb, w, l, gamesBack }: {
  posture: WindowPosture
  rationale: string
  playoffProb: number
  w: number
  l: number
  gamesBack: number
}) {
  const cfg = POSTURE[posture]
  const Icon = cfg.Icon
  const probColor = playoffProb > 0.65 ? 'text-positive-400' : playoffProb > 0.35 ? 'text-accent-300' : 'text-negative-400'
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative overflow-hidden rounded-lg border p-5 ${cfg.bg} ${cfg.border} ${cfg.glow}`}
    >
      {/* corner brackets */}
      <span className={`absolute left-2 top-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>┌─</span>
      <span className={`absolute right-2 top-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>─┐</span>
      <span className={`absolute bottom-2 left-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>└─</span>
      <span className={`absolute bottom-2 right-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>─┘</span>
      <div className="flex items-start gap-5">
        {/* Icon */}
        <div className={`grid h-16 w-16 shrink-0 place-items-center rounded-xl border-2 ${cfg.border} ${cfg.bg}`}>
          <Icon className={`h-8 w-8 ${cfg.color}`} strokeWidth={2.5} />
        </div>

        {/* Main content */}
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <PulseDot color={cfg.dot} />
            <span className={`font-mono text-[9px] font-semibold uppercase tracking-[0.3em] ${cfg.color} opacity-80`}>
              WINDOW ASSESSMENT
            </span>
            <Cite cite={{ label: 'Window Posture', detail: 'Derived from W-L record, division gap, games back, and payroll flexibility. Buy = contention-window team with room to add; Sell = out of contention; Hold = ambiguous.' }} />
          </div>
          <div className={`display text-[38px] font-black leading-none tracking-tight ${cfg.color}`}>
            {cfg.label}
          </div>
          <p className="mt-2 max-w-xl text-[11px] leading-relaxed text-ink-300">{rationale}</p>

          {/* Record strip */}
          <div className="mt-3 flex items-center gap-5">
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[22px] font-black leading-none text-ink-100 tabular">{w}–{l}</span>
              <span className="font-mono text-[10px] text-ink-500">W-L</span>
            </div>
            <div className="h-6 w-px bg-ink-700" />
            <div className="flex items-baseline gap-1">
              <span className={`font-mono text-[18px] font-black leading-none tabular ${gamesBack === 0 ? 'text-positive-400' : gamesBack > 8 ? 'text-negative-400' : 'text-ink-200'}`}>
                {gamesBack === 0 ? '—' : gamesBack}
              </span>
              <span className="font-mono text-[10px] text-ink-500">{gamesBack === 0 ? 'DIV LEAD' : 'GB'}</span>
            </div>
            <div className="h-6 w-px bg-ink-700" />
            <div className="flex items-baseline gap-1">
              <span className={`font-mono text-[18px] font-black leading-none tabular ${probColor}`}>
                {Math.round(playoffProb * 100)}%
              </span>
              <span className="font-mono text-[9px] text-ink-500 flex items-center gap-0.5">
                P(PLAYOFF)
                <Cite cite={{ label: 'Playoff Probability', detail: 'Logistic model: win%, games back, games remaining. 12 of 30 teams qualify. Not market-implied — heuristic only.' }} />
              </span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  )
}
