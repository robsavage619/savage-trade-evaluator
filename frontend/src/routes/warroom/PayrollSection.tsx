import { useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine,
} from 'recharts'
import type { CurrentPlayer } from '../../data/players'
import { forecastArb } from '../../lib/arbForecast'
import { advanceArbClass, money } from './shared'
import { AnimatedNumber, Cite } from './primitives'

// ── payroll gauge ────────────────────────────────────────────────────────────

const CBT_TIERS = [
  { label: 'T1', offset: 0,          rate: '20%',   color: '#ff8a3d' },
  { label: 'T2', offset: 20_000_000, rate: '32%',   color: '#ff6b3d' },
  { label: 'T3', offset: 40_000_000, rate: '62.5%', color: '#ff5d73' },
]

export function PayrollGauge({ committed, threshold, headroom }: { committed: number; threshold: number; headroom: number }) {
  // Scale bar to T3 + $20M so all markers are visible
  const scale = threshold + 60_000_000
  const filledPct = Math.min(100, (committed / scale) * 100)
  const over = committed > threshold

  // Which tier is the team in?
  const overBy = committed - threshold
  const activeTier = overBy <= 0 ? null : overBy < 20_000_000 ? 0 : overBy < 40_000_000 ? 1 : 2
  const barColor = activeTier === null ? '#3ddc97' : CBT_TIERS[activeTier].color

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Payroll vs CBT</span>
        <div className="flex items-center gap-2">
          {activeTier !== null && (
            <span className="font-mono text-[9px] font-semibold" style={{ color: CBT_TIERS[activeTier].color }}>
              TIER {activeTier + 1} · {CBT_TIERS[activeTier].rate} TAX
            </span>
          )}
          <span className={`font-mono text-[10px] font-semibold ${over ? 'text-negative-500' : 'text-positive-500'}`}>
            {over ? 'OVER CBT' : 'UNDER CBT'}
          </span>
        </div>
      </div>
      {/* Bar */}
      <div className="relative mb-1 h-3 overflow-hidden rounded-full bg-ink-800">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${filledPct}%` }}
          transition={{ duration: 1.0, ease: 'easeOut' }}
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ background: barColor, boxShadow: `0 0 10px ${barColor}60` }}
        />
        {/* Tier markers */}
        {CBT_TIERS.map((tier) => {
          const markerPct = ((threshold + tier.offset) / scale) * 100
          return (
            <div
              key={tier.label}
              className="absolute inset-y-0 w-px opacity-70"
              style={{ left: `${markerPct}%`, background: tier.color }}
            />
          )
        })}
      </div>
      {/* Tier labels */}
      <div className="relative mb-2 h-4">
        {CBT_TIERS.map((tier) => {
          const markerPct = ((threshold + tier.offset) / scale) * 100
          return (
            <div
              key={tier.label}
              className="absolute -translate-x-1/2 font-mono text-[8px] font-semibold"
              style={{ left: `${markerPct}%`, color: tier.color, opacity: 0.7 }}
            >
              {tier.label}
            </div>
          )
        })}
      </div>
      <div className="flex items-end justify-between">
        <div>
          <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-500 mb-0.5">Committed / Threshold</div>
          <div className="font-mono text-[12px] text-ink-200">
            <AnimatedNumber end={committed / 1_000_000} decimals={1} prefix="$" suffix="M" />
            <span className="text-ink-600"> / </span>
            <span className="text-ink-400">{money(threshold)}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="flex items-center justify-end gap-1 mb-0.5">
            <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-ink-500">Headroom</span>
            <Cite cite={{ label: 'CBT Headroom', detail: 'Dollars under (positive) or over (negative) the Competitive Balance Tax threshold. Overage triggers luxury tax at the active tier — T1 20%, T2 32%, T3 62.5%.' }} />
          </div>
          <div className={`font-mono text-[28px] font-black leading-none tabular ${over ? 'text-negative-500' : 'text-positive-400'}`}>
            {over ? '−' : '+'}
            <AnimatedNumber end={Math.abs(headroom) / 1_000_000} decimals={1} suffix="M" />
          </div>
        </div>
      </div>
    </div>
  )
}

// ── payroll timeline ──────────────────────────────────────────────────────────

const PAYROLL_YEARS = ['2026', '2027', '2028']

function PayrollTooltip({ active, payload, label }: { active?: boolean; payload?: {color: string; name: string; value: number}[]; label?: string }) {
  if (!active || !payload) return null
  const total = payload.reduce((s, p) => s + p.value, 0)
  return (
    <div className="rounded border border-ink-700 bg-ink-900 p-2 text-[10px]">
      <div className="mb-1 font-mono font-semibold text-ink-200">{label}</div>
      {payload.map(p => (
        <div key={p.name} className="flex justify-between gap-3">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="font-mono text-ink-300">${p.value.toFixed(1)}M</span>
        </div>
      ))}
      <div className="mt-1 border-t border-ink-700 pt-1 flex justify-between gap-3">
        <span className="text-ink-400">Total</span>
        <span className="font-mono font-bold text-ink-100">${total.toFixed(1)}M</span>
      </div>
    </div>
  )
}

export function PayrollTimeline({ players, cbtThreshold }: { players: CurrentPlayer[]; cbtThreshold: number }) {
  const data = useMemo(() => {
    return PAYROLL_YEARS.map((yr, t) => {
      let preArb = 0, arb = 0, fa = 0
      for (const p of players) {
        const forecast = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
        const cls = advanceArbClass(forecast.currentClass, t)
        const cost = forecast.projections[t] ?? forecast.projections[2]
        if (cls === 'pre-arb') preArb += cost
        else if (cls !== 'fa') arb += cost
        else fa += cost
      }
      return {
        year: yr,
        'Pre-Arb': +(preArb / 1e6).toFixed(1),
        'Arb': +(arb / 1e6).toFixed(1),
        'FA/Vet': +(fa / 1e6).toFixed(1),
        total: (preArb + arb + fa) / 1e6,
      }
    })
  }, [players])

  const cbtM = cbtThreshold / 1e6
  const maxVal = Math.max(...data.map(d => d.total), cbtM) * 1.15

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
          Payroll Projection
        </span>
        <span className="font-mono text-[8.5px] text-ink-600">3-year forecast · full roster · arb path</span>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -8 }} barCategoryGap="25%">
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2238" vertical={false} />
          <XAxis dataKey="year" tick={{ fill: '#8a96c0', fontSize: 10, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
          <YAxis
            tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }}
            tickFormatter={v => `$${v}M`}
            axisLine={false} tickLine={false}
            domain={[0, maxVal]}
          />
          <Tooltip content={<PayrollTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          <ReferenceLine y={cbtM} stroke="#ff5d73" strokeDasharray="4 2" strokeWidth={1}
            label={{ value: 'CBT', fill: '#ff5d73', fontSize: 9, fontFamily: 'JetBrains Mono', position: 'insideTopRight' }} />
          <Bar dataKey="Pre-Arb" stackId="a" fill="#3ddc97" fillOpacity={0.7} radius={[0,0,0,0]} />
          <Bar dataKey="Arb" stackId="a" fill="#ff8a3d" fillOpacity={0.7} />
          <Bar dataKey="FA/Vet" stackId="a" fill="#8a96c0" fillOpacity={0.5} radius={[3,3,0,0]} />
        </BarChart>
      </ResponsiveContainer>
      <div className="mt-2 flex gap-4">
        {[['#3ddc97', 'Pre-Arb'], ['#ff8a3d', 'Arb'], ['#8a96c0', 'FA/Vet']].map(([color, label]) => (
          <div key={label} className="flex items-center gap-1">
            <span className="h-2 w-2 rounded-sm" style={{ background: color, opacity: 0.7 }} />
            <span className="font-mono text-[8.5px] text-ink-500">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
