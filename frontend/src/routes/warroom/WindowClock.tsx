import { useMemo } from 'react'
import { motion } from 'framer-motion'
import type { CurrentPlayer } from '../../data/players'
import { parseArbClass } from '../../lib/arbForecast'
import { agingDelta } from '../../lib/hypothetical'
import { advanceArbClass, ARB_CLASS_LABEL, ARB_CLASS_COLOR } from './shared'

// ── window clock ──────────────────────────────────────────────────────────────

const WINDOW_YEARS = [2026, 2027, 2028, 2029, 2030, 2031]

function warCellStyle(war: number): { bg: string; text: string } {
  if (war > 4.5) return { bg: 'bg-positive-500/25 ring-1 ring-positive-500/40', text: 'text-positive-200' }
  if (war > 3.0) return { bg: 'bg-positive-500/15', text: 'text-positive-300' }
  if (war > 1.5) return { bg: 'bg-positive-500/8',  text: 'text-positive-400' }
  if (war > 0.5) return { bg: 'bg-accent-500/10',   text: 'text-accent-400' }
  if (war > 0.0) return { bg: 'bg-ink-800/80',      text: 'text-ink-500' }
  return { bg: 'bg-ink-900/40', text: 'text-ink-700' }
}

export function WindowClock({ players }: { players: CurrentPlayer[] }) {
  const core = useMemo(() => {
    return [...players]
      .filter(p => (p.last_war ?? 0) > 0.3 && p.age != null)
      .sort((a, b) => (b.last_war ?? 0) - (a.last_war ?? 0))
      .slice(0, 10)
  }, [players])

  const rows = useMemo(() => core.map(p => {
    const age0 = p.age!
    const baseWar = Math.max(0, p.last_war ?? 0.5)
    const cls0 = parseArbClass(p.contract_status)
    let war = baseWar
    const years = WINDOW_YEARS.map((yr, t) => {
      war = Math.max(0, war + agingDelta(age0 + t))
      const cls = advanceArbClass(cls0, t + 1)
      return { yr, war, cls }
    })
    return { player: p, years }
  }), [core])

  // team totals per year
  const totals = WINDOW_YEARS.map((_, t) =>
    rows.reduce((sum, r) => sum + r.years[t].war, 0)
  )

  if (rows.length === 0) return null

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 font-mono text-[8.5px] text-ink-600">projected WAR · top 10 contributors · aging curve applied</div>

      {/* Header */}
      <div className="mb-1 grid items-center gap-0.5" style={{ gridTemplateColumns: '8rem repeat(6, 1fr)' }}>
        <div />
        {WINDOW_YEARS.map(yr => (
          <div key={yr} className="text-center font-mono text-[9px] font-semibold text-ink-500">{yr}</div>
        ))}
      </div>

      {/* Player rows */}
      <div className="space-y-0.5">
        {rows.map(({ player: p, years }) => (
          <motion.div
            key={p.mlb_player_id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            className="grid items-center gap-0.5"
            style={{ gridTemplateColumns: '8rem repeat(6, 1fr)' }}
          >
            {/* Player name */}
            <div className="flex min-w-0 items-center gap-1 pr-2">
              <span className="truncate font-mono text-[10px] text-ink-200">{p.name.split(' ').slice(-1)[0]}</span>
              <span className="shrink-0 font-mono text-[8px] text-ink-600">{p.position_abbr ?? '?'}</span>
            </div>
            {/* Year cells */}
            {years.map(({ yr, war, cls }) => {
              const { bg, text } = warCellStyle(war)
              return (
                <div
                  key={yr}
                  title={`${p.name} · ${yr} · ${war.toFixed(1)} WAR · ${ARB_CLASS_LABEL[cls]}`}
                  className={`flex flex-col items-center justify-center rounded py-0.5 ${bg}`}
                >
                  <span className={`font-mono text-[10px] font-bold tabular leading-none ${text}`}>
                    {war > 0 ? war.toFixed(1) : '—'}
                  </span>
                  <span className={`font-mono text-[7px] leading-none ${ARB_CLASS_COLOR[cls]}`}>
                    {ARB_CLASS_LABEL[cls]}
                  </span>
                </div>
              )
            })}
          </motion.div>
        ))}

        {/* Total row */}
        <div className="mt-1 grid items-center gap-0.5 border-t border-ink-700/50 pt-1"
          style={{ gridTemplateColumns: '8rem repeat(6, 1fr)' }}>
          <span className="font-mono text-[9px] font-semibold uppercase tracking-wider text-ink-500">Core total</span>
          {totals.map((tot, t) => {
            const { text } = warCellStyle(tot / 5) // normalize to per-player for coloring
            return (
              <div key={t} className="text-center">
                <span className={`font-mono text-[10px] font-black tabular ${text}`}>{tot.toFixed(0)}</span>
              </div>
            )
          })}
        </div>
      </div>

    </div>
  )
}
