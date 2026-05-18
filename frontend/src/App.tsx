import { Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Activity, ArrowRightLeft, Building2, Briefcase, FlaskConical, Hammer } from 'lucide-react'
import PresslyCase from './routes/PresslyCase'
import Research from './routes/Research'
import TradeWorkspace from './routes/TradeWorkspace'
import OrgExplorer from './routes/OrgExplorer'
import TradeBuilder from './routes/TradeBuilder'
import OrgScout from './routes/OrgScout'
import PlayerProfile from './routes/PlayerProfile'
import { PRESSLY_TRADE_ID } from './data'
import { TeamIdentitySwitcher } from './components/TeamIdentitySwitcher'

function TopNav() {
  const loc = useLocation()
  const items = [
    { to: '/build', label: 'Trade Builder', icon: Hammer },
    { to: `/trade/${PRESSLY_TRADE_ID}`, label: 'Pipeline', icon: ArrowRightLeft },
    { to: '/orgs', label: 'Org Explorer', icon: Building2 },
    { to: '/case/pressly', label: 'Case Study', icon: Briefcase },
    { to: '/research', label: 'Research', icon: FlaskConical },
  ]
  return (
    <header className="sticky top-0 z-50 border-b border-ink-700 bg-ink-950/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1480px] items-center justify-between gap-6 px-6 py-3">
        <NavLink to="/case/pressly" className="flex items-center gap-2.5">
          <div className="grid h-7 w-7 place-items-center rounded-md bg-accent-500/15 text-accent-400">
            <Activity className="h-4 w-4" strokeWidth={2.5} />
          </div>
          <div className="leading-tight">
            <div className="text-[13px] font-semibold tracking-tight text-ink-100">Savage Trade Evaluator</div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Baseball Operations · v0.1</div>
          </div>
        </NavLink>
        <nav className="flex items-center gap-1">
          {items.map(({ to, label, icon: Icon }) => {
            const base = to.split('/').slice(0, 3).join('/')
            const active = loc.pathname.startsWith(base.replace(/\/\d+$/, ''))
            return (
              <NavLink
                key={to}
                to={to}
                className={`group relative flex items-center gap-2 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors ${
                  active ? 'text-ink-100' : 'text-ink-300 hover:text-ink-100'
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
                {active ? (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 -z-10 rounded-md bg-ink-700/80 ring-1 ring-ink-600"
                    transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                  />
                ) : null}
              </NavLink>
            )
          })}
        </nav>
        <div className="hidden items-center gap-2 md:flex">
          <TeamIdentitySwitcher />
        </div>
      </div>
    </header>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-ink-950">
      <TopNav />
      <Routes>
        <Route path="/" element={<Navigate to="/build" replace />} />
        <Route path="/build" element={<TradeBuilder />} />
        <Route path="/case/pressly" element={<PresslyCase />} />
        <Route path="/trade/:id" element={<TradeWorkspace />} />
        <Route path="/orgs" element={<OrgExplorer />} />
        <Route path="/orgs/:bref" element={<OrgScout />} />
        <Route path="/research" element={<Research />} />
        <Route path="/player/:id" element={<PlayerProfile />} />
        <Route path="*" element={<Navigate to="/build" replace />} />
      </Routes>
      <footer className="border-t border-ink-700 px-6 py-6 text-[11px] text-ink-400">
        <div className="mx-auto flex max-w-[1480px] flex-wrap items-center justify-between gap-3">
          <span>
            Sources: MLB Stats API · Baseball Reference · Baseball Savant Statcast · 27 tables · 1.29M rows
          </span>
          <span className="mono">
            Posteriors illustrative pre-V2 model · naive baseline = $/WAR (D-11)
          </span>
        </div>
      </footer>
    </div>
  )
}
