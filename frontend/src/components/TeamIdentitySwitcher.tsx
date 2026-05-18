import { useEffect, useRef, useState } from 'react'
import { ChevronDown, Check, Search } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useRoster, useTeamsByBref } from '../lib/rosterStore'
import { TEAM_THEME, useIdentityStore } from '../lib/identityStore'
import { TeamLogo } from './TeamLogo'

export function TeamIdentitySwitcher() {
  const active = useIdentityStore((s) => s.activeTeam)
  const setActive = useIdentityStore((s) => s.setActiveTeam)
  const roster = useRoster()
  const teamsByBref = useTeamsByBref()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const team = teamsByBref[active] ?? teamsByBref.NYM
  const theme = TEAM_THEME[active] ?? TEAM_THEME.NYM
  const q = query.trim().toLowerCase()
  const filtered = q
    ? roster.teams.filter((t) => t.bref.toLowerCase().includes(q) || t.name.toLowerCase().includes(q))
    : roster.teams

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-md border border-ink-700 bg-ink-800/70 py-1 pl-1.5 pr-2 transition-colors hover:border-ink-500"
        style={{ boxShadow: `inset 0 0 0 1px ${theme.primary}22` }}
      >
        <TeamLogo team={team.bref} size={22} />
        <div className="text-left leading-tight">
          <div className="text-[9px] uppercase tracking-[0.16em] text-ink-400">You are</div>
          <div className="text-[11px] font-semibold text-ink-100">{team.bref} · {team.name.replace(/^(New York|Los Angeles|San Francisco|San Diego|Chicago|St\. Louis|Washington|Kansas City) /, '')}</div>
        </div>
        <ChevronDown className={`h-3 w-3 text-ink-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-[calc(100%+6px)] z-50 w-[320px] overflow-hidden rounded-lg border border-ink-700 bg-ink-900 shadow-[0_24px_60px_rgba(0,0,0,0.6)]"
          >
            <div className="border-b border-ink-700 p-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
                <input
                  autoFocus
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Switch identity…"
                  className="w-full rounded-md border border-ink-700 bg-ink-800/80 py-1.5 pl-7 pr-2 text-[12px] text-ink-100 placeholder:text-ink-400 focus:border-accent-500/50 focus:outline-none"
                />
              </div>
            </div>
            <ul className="max-h-[340px] overflow-y-auto py-1">
              {filtered.map((t) => {
                const isActive = t.bref === active
                const tt = TEAM_THEME[t.bref] ?? { primary: '#ff8a3d', secondary: '#111' }
                return (
                  <li key={t.bref}>
                    <button
                      onClick={() => {
                        setActive(t.bref)
                        setOpen(false)
                      }}
                      className={`flex w-full items-center gap-2.5 px-2.5 py-1.5 text-left transition-colors ${
                        isActive ? 'bg-ink-800' : 'hover:bg-ink-800/60'
                      }`}
                    >
                      <TeamLogo team={t.bref} size={22} />
                      <div className="flex-1 leading-tight">
                        <div className="text-[12px] font-semibold text-ink-100">{t.name}</div>
                        <div className="mono text-[10px] text-ink-400">{t.bref} · {t.roster_count} players</div>
                      </div>
                      <span className="h-3 w-3 rounded-full" style={{ background: tt.primary, boxShadow: `0 0 0 2px ${tt.secondary}` }} />
                      {isActive && <Check className="h-3.5 w-3.5 text-accent-400" />}
                    </button>
                  </li>
                )
              })}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
