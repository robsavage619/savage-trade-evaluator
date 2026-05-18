import { motion } from 'framer-motion'
import type { Coach, FrontOffice } from '../types'
import { teamColor } from '../lib/format'
import { TeamLogo } from './TeamLogo'

type Props = {
  team: string
  teamName: string
  coaches: Coach[]
  fo: FrontOffice[]
  side: 'left' | 'right'
  highlightedNames?: string[]
}

const ROLE_ORDER: Array<{ key: string; label: string; from: 'fo' | 'coach' }> = [
  { key: 'President', label: 'POBO / Pres', from: 'fo' },
  { key: 'General Manager', label: 'GM', from: 'fo' },
  { key: 'Manager', label: 'Manager', from: 'fo' },
  { key: 'COAP', label: 'Pitching Coach', from: 'coach' },
  { key: 'COAT', label: 'Hitting Coach', from: 'coach' },
  { key: 'COAB', label: 'Bench Coach', from: 'coach' },
  { key: 'Farm Director', label: 'Farm Director', from: 'fo' },
  { key: 'Scouting Director', label: 'Scouting Director', from: 'fo' },
]

export function PersonnelTriangle({ team, teamName, coaches, fo, side, highlightedNames = [] }: Props) {
  const color = teamColor(team)
  const teamCoaches = coaches.filter((c) => c.team_bref === team)
  const teamFo = fo.filter((f) => f.team_bref === team)

  const rows = ROLE_ORDER.map(({ key, label, from }) => {
    const name =
      from === 'fo'
        ? teamFo.find((f) => f.role === key)?.person_name
        : teamCoaches.find((c) => c.job_code === key)?.person_name
    return { label, name: name ?? '—', highlight: name ? highlightedNames.includes(name) : false }
  })

  return (
    <div
      className="card relative p-4"
      style={{ borderColor: 'rgba(255,255,255,0.06)' }}
    >
      <div className="absolute left-0 right-0 top-0 h-[2px]" style={{ background: color.primary }} aria-hidden />
      <div className={`mb-3 flex items-center justify-between ${side === 'right' ? 'flex-row-reverse' : ''}`}>
        <div className={`flex items-center gap-3 ${side === 'right' ? 'flex-row-reverse text-right' : ''}`}>
          <TeamLogo team={team} size={36} />
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.16em] text-ink-400">
              {side === 'left' ? 'Sending' : 'Receiving'} · {team}
            </div>
            <div className="text-[14px] font-semibold tracking-tight text-ink-100">{teamName}</div>
          </div>
        </div>
        <div
          className="mono rounded-md px-2 py-1 text-[11px] font-semibold tabular"
          style={{ background: color.soft, color: color.primary }}
        >
          {team}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-1.5">
        {rows.map((r, i) => (
          <motion.div
            key={r.label}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.04 * i, duration: 0.25 }}
            className={`flex items-center justify-between gap-3 rounded-md border px-2.5 py-1.5 ${
              r.highlight
                ? 'border-accent-500/45 bg-accent-500/10'
                : 'border-transparent bg-ink-800/40 hover:border-ink-600'
            }`}
          >
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">{r.label}</div>
            <div className={`mono text-[12px] tabular ${r.highlight ? 'text-accent-300' : 'text-ink-100'}`}>{r.name}</div>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
