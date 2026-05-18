import { Routes, Route, Navigate, NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRightLeft, Building2, Briefcase, FlaskConical, Hammer } from 'lucide-react'
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
        <NavLink to="/" className="group flex items-center gap-3 select-none">
          {/* Badge */}
          <div className="relative flex-shrink-0">
            {/* Spinning outer ring */}
            <div className="nameplate-ring absolute -inset-[4px]" />
            {/* Soft halo behind badge */}
            <div className="absolute inset-0 rounded-xl blur-[6px] opacity-60"
              style={{ background: 'radial-gradient(circle, #ff6a13 0%, transparent 75%)' }} />
            {/* Badge body */}
            <div className="nameplate-badge relative grid h-9 w-9 place-items-center rounded-xl"
              style={{ filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.5))' }}>
              <span style={{
                fontFamily: 'var(--font-sans)', fontSize: 12, fontWeight: 800,
                color: 'white', letterSpacing: '-0.03em', lineHeight: 1,
                textShadow: '0 1px 3px rgba(0,0,0,0.4)',
              }}>SA</span>
            </div>
          </div>
          {/* Wordmark */}
          <div className="leading-none">
            <div className="nameplate-text text-[15px] font-bold tracking-[-0.02em]">
              Savage Analytics
            </div>
            <div className="mt-[3px] text-[9px] font-semibold uppercase tracking-[0.22em] text-ink-500">
              Baseball Intelligence
            </div>
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
            Savage Analytics · Posteriors illustrative pre-V2 model · naive baseline = $/WAR (D-11)
          </span>
        </div>
      </footer>
    </div>
  )
}
