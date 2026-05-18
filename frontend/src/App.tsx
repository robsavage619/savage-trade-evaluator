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

function ClaudeLogo({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <path
        d="M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z"
        fill="#D97757"
        fillRule="nonzero"
      />
    </svg>
  )
}

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
      <div className="flex items-center justify-center gap-1.5 border-b border-ink-800/50 py-1 text-[11px] text-ink-500">
        <ClaudeLogo size={13} />
        <span>Powered by Claude</span>
      </div>
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
