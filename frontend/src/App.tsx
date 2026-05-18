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
          {/* Geometric mark — scatter trend */}
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden>
            {/* Regression trend line */}
            <line x1="4" y1="27" x2="28" y2="5"
              stroke="#ff8a3d" strokeWidth="1" strokeOpacity="0.35"
              strokeDasharray="3 2.5" strokeLinecap="round" />
            {/* Data nodes — ascending scatter */}
            <circle cx="4"  cy="26" r="2"   fill="#e0e5f4" fillOpacity="0.25" />
            <circle cx="12" cy="20" r="2"   fill="#e0e5f4" fillOpacity="0.35" />
            <circle cx="20" cy="13" r="2"   fill="#e0e5f4" fillOpacity="0.5"  />
            {/* Top-right node — the credible finding */}
            <circle cx="27" cy="7"  r="2.5" fill="#ff8a3d" />
          </svg>
          {/* Separator */}
          <div style={{ width: 1, height: 26, background: 'var(--color-ink-700)', flexShrink: 0 }} />
          {/* Wordmark */}
          <div className="leading-none">
            <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--color-ink-100)' }}>
              Savage Analytics
            </div>
            <div style={{ fontSize: 9, fontWeight: 500, letterSpacing: '0.18em', color: 'var(--color-ink-500)', textTransform: 'uppercase', marginTop: 3 }}>
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
