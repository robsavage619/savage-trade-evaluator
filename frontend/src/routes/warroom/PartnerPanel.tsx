import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import type { TeamPayload } from '../../data/warroom/types'
import { warRoomIndex } from '../../lib/warroomData'
import { TeamLogo } from '../../components/TeamLogo'
import { POSTURE, money } from './shared'
import { HolesBoard } from './RosterShape'

export function PartnerPanel({ bref, payload, onClose }: {
  bref: string
  payload: TeamPayload | null
  onClose: () => void
}) {
  const idx = warRoomIndex.teams.find(t => t.code === bref)
  if (!idx) return null
  const cfg = POSTURE[idx.windowPosture]
  const Icon = cfg.Icon

  return (
    <motion.div
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      className={`rounded-lg border p-4 ${cfg.bg} ${cfg.border} ${cfg.glow}`}
    >
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <TeamLogo team={bref} size={32} />
          <div>
            <div className="flex items-center gap-2">
              <span className="display text-[18px] font-black text-ink-100">{bref}</span>
              <span className={`flex items-center gap-1 font-mono text-[10px] font-bold ${cfg.color}`}>
                <Icon className="h-3 w-3" />{idx.windowPosture.toUpperCase()}
              </span>
            </div>
            <div className="font-mono text-[10px] text-ink-300">
              {idx.w}–{idx.l} · {idx.gamesBack === 0 ? 'Div leader' : `${idx.gamesBack} GB`} · {idx.division}
            </div>
          </div>
        </div>
        <button onClick={onClose} className="rounded p-1 text-ink-600 hover:text-ink-200 transition-colors">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Payroll */}
      <div className="mb-3 flex gap-4 font-mono text-[11px]">
        <span className="text-ink-400">Payroll <span className="text-ink-100">{money(idx.payrollCommitted)}</span></span>
        <span className={idx.payrollHeadroom < 0 ? 'text-negative-400' : 'text-positive-400'}>
          Hdroom {money(idx.payrollHeadroom)}
        </span>
      </div>

      {payload ? (
        <>
          {payload.context.postureRationale && (
            <p className="mb-3 text-[11px] leading-relaxed text-ink-300">{payload.context.postureRationale}</p>
          )}
          <HolesBoard
            holes={payload.holes}
            surpluses={payload.surpluses}
          />
          {payload.context.expiringContracts.length > 0 && (
            <div className="mt-3 rounded-lg border border-ink-700 bg-ink-900/60 p-3">
              <div className="mb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Their commitments</div>
              <div className="space-y-1">
                {payload.context.expiringContracts.map(c => (
                  <div key={c.player} className="flex items-center justify-between text-[11px]">
                    <span className="truncate text-ink-200">{c.player}</span>
                    <span className="font-mono shrink-0 text-ink-300">{money(c.capHit)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="space-y-2 animate-pulse" aria-label={`Loading ${bref} intel`}>
          <div className="h-3 w-3/4 rounded bg-ink-800" />
          <div className="h-3 w-full rounded bg-ink-800" />
          <div className="h-3 w-5/6 rounded bg-ink-800" />
          <div className="mt-3 h-16 w-full rounded bg-ink-800" />
          <div className="h-3 w-2/3 rounded bg-ink-800" />
          <div className="h-3 w-full rounded bg-ink-800" />
        </div>
      )}
    </motion.div>
  )
}
