import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import { warRoomIndex } from '../../lib/warroomData'
import { POSTURE, DIVISIONS } from './shared'

export function LeagueTicker({ yourBref, partnerBref, onSelect }: {
  yourBref: string
  partnerBref: string | null
  onSelect: (bref: string) => void
}) {
  const byDiv = useMemo(() => {
    const map: Record<string, typeof warRoomIndex.teams> = {}
    for (const t of warRoomIndex.teams) {
      if (!map[t.division]) map[t.division] = []
      map[t.division].push(t)
    }
    return map
  }, [])

  return (
    <div className="space-y-3">
      {DIVISIONS.map((div) => (
        <div key={div}>
          <div className="mb-1 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-ink-500">{div}</div>
          <div className="space-y-0.5">
            {(byDiv[div] ?? []).map((t) => {
              const cfg = POSTURE[t.windowPosture]
              const isYou = t.code === yourBref
              const isPartner = t.code === partnerBref
              return (
                <motion.button
                  key={t.code}
                  onClick={() => !isYou && onSelect(t.code)}
                  disabled={isYou}
                  whileHover={!isYou ? { x: 2 } : undefined}
                  className={`group flex w-full items-center gap-2 rounded px-2 py-1 text-left transition-colors ${
                    isYou
                      ? 'cursor-default bg-accent-500/10 text-accent-300'
                      : isPartner
                      ? 'bg-ink-700/80 text-ink-100'
                      : 'text-ink-300 hover:bg-ink-800/60 hover:text-ink-100'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${cfg.dot} ${isYou || isPartner ? 'opacity-100' : 'opacity-60'}`} />
                  <span className="font-mono w-7 shrink-0 text-[11px] font-bold">{t.code}</span>
                  <span className="font-mono text-[10px] tabular text-ink-400">{t.w}–{t.l}</span>
                  <span className={`font-mono ml-auto text-[9px] font-semibold ${cfg.color} ${isYou || isPartner ? 'opacity-100' : 'opacity-70'}`}>
                    {t.windowPosture.toUpperCase()}
                  </span>
                  {isYou && <span className="font-mono text-[8px] text-accent-400">YOU</span>}
                  {isPartner && <ChevronRight className="h-3 w-3 text-ink-400" />}
                </motion.button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
