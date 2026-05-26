import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip,
  CartesianGrid, ReferenceLine, Cell, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  AreaChart, Area,
} from 'recharts'
import {
  AlertTriangle, Sparkles, Eye, Shield, Clock, Zap, Phone, ArrowLeftRight,
  ArrowRight, DollarSign, Activity,
} from 'lucide-react'
import { TeamLogo } from './TeamLogo'
import type {
  AnalysisReport, AnalysisVerdict, FindingKind, Horizon, MatrixCategory,
  Materiality, Tier, SellerMotivation, Overpay, Posture, PackagePlayer,
} from '../lib/analysisPrompt'

const VERDICT_CFG: Record<AnalysisVerdict, { label: string; color: string; bg: string; border: string }> = {
  'aggressive-buy':  { label: 'AGGRESSIVE BUY',  color: '#3ddc97', bg: 'bg-positive-500/10', border: 'border-positive-500/40' },
  'selective-buy':   { label: 'SELECTIVE BUY',   color: '#5fd3a8', bg: 'bg-positive-500/8',  border: 'border-positive-500/30' },
  'hold-and-assess': { label: 'HOLD & ASSESS',   color: '#ff8a3d', bg: 'bg-accent-500/10',   border: 'border-accent-500/40' },
  'soft-sell':       { label: 'SOFT SELL',       color: '#ff6b3d', bg: 'bg-accent-500/10',   border: 'border-accent-500/30' },
  'full-teardown':   { label: 'FULL TEARDOWN',   color: '#ff5d73', bg: 'bg-negative-500/10', border: 'border-negative-500/40' },
}
const FINDING_CFG: Record<FindingKind, { color: string; bg: string; Icon: typeof AlertTriangle }> = {
  critical:    { color: '#ff5d73', bg: 'bg-negative-500/8', Icon: AlertTriangle },
  opportunity: { color: '#3ddc97', bg: 'bg-positive-500/8', Icon: Sparkles },
  watch:       { color: '#ff8a3d', bg: 'bg-accent-500/8',   Icon: Eye },
  strength:    { color: '#5b9dff', bg: 'bg-[#5b9dff]/8',    Icon: Shield },
}
const CATEGORY_CFG: Record<MatrixCategory, { color: string; label: string }> = {
  acquire:      { color: '#3ddc97', label: 'Acquire' },
  'trade-away': { color: '#ff5d73', label: 'Trade away' },
  extend:       { color: '#5b9dff', label: 'Extend' },
  hold:         { color: '#8a96c0', label: 'Hold' },
}
const HORIZON_LABEL: Record<Horizon, string> = { now: 'NOW', deadline: 'DEADLINE', offseason: 'OFFSEASON', 'multi-year': 'MULTI-YEAR' }
const MATERIALITY_CFG: Record<Materiality, { color: string; bg: string; border: string; label: string }> = {
  quiet:   { color: '#8a96c0', bg: 'bg-ink-800/40',      border: 'border-ink-700',          label: 'QUIET' },
  notable: { color: '#ff8a3d', bg: 'bg-accent-500/[0.07]', border: 'border-accent-500/30',   label: 'NOTABLE' },
  urgent:  { color: '#ff5d73', bg: 'bg-negative-500/[0.07]', border: 'border-negative-500/40', label: 'URGENT' },
}
const TIER_CFG: Record<Tier, { label: string; color: string }> = {
  primary:     { label: 'PRIMARY', color: '#3ddc97' },
  fallback:    { label: 'FALLBACK', color: '#ff8a3d' },
  'dart-throw':{ label: 'DART THROW', color: '#8a96c0' },
}
const MOTIVATION_CFG: Record<SellerMotivation, { label: string; color: string }> = {
  forced:        { label: 'FORCED', color: '#3ddc97' },
  opportunistic: { label: 'OPPORTUNISTIC', color: '#5b9dff' },
  reluctant:     { label: 'RELUCTANT', color: '#ff8a3d' },
  unknown:       { label: 'UNKNOWN', color: '#8a96c0' },
}
const OVERPAY_CFG: Record<Overpay, { label: string; color: string }> = {
  'you-win':     { label: 'YOU WIN', color: '#3ddc97' },
  fair:          { label: 'FAIR', color: '#8a96c0' },
  'you-overpay': { label: 'YOU OVERPAY', color: '#ff5d73' },
}
const POSTURE_COLOR: Record<Posture, string> = { buy: '#3ddc97', hold: '#ff8a3d', sell: '#ff5d73' }

// ── confidence ring ────────────────────────────────────────────────────────────

function ConfidenceRing({ value, color }: { value: number; color: string }) {
  const r = 26
  const circ = 2 * Math.PI * r
  return (
    <div className="relative grid h-[68px] w-[68px] place-items-center">
      <svg width={68} height={68} className="-rotate-90">
        <circle cx={34} cy={34} r={r} fill="none" stroke="#1a2238" strokeWidth={5} />
        <motion.circle
          cx={34} cy={34} r={r} fill="none" stroke={color} strokeWidth={5} strokeLinecap="round"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: circ - (value / 100) * circ }}
          transition={{ duration: 1.1, ease: 'easeOut' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="font-mono text-[16px] font-black leading-none" style={{ color }}>{Math.round(value)}</span>
        <span className="font-mono text-[7px] uppercase tracking-wider text-ink-600">conf</span>
      </div>
    </div>
  )
}

function SectionLabel({ children, sub }: { children: React.ReactNode; sub?: string }) {
  return (
    <div className="mb-2 flex items-center gap-2">
      <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">{children}</span>
      {sub && <span className="font-mono text-[8.5px] text-ink-600">{sub}</span>}
    </div>
  )
}

// ── today's move ────────────────────────────────────────────────────────────────

function TodaysMove({ move }: { move: NonNullable<AnalysisReport['todaysMove']> }) {
  const cfg = MATERIALITY_CFG[move.materiality]
  const quiet = move.materiality === 'quiet'
  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
      className={`rounded-lg border p-4 ${cfg.bg} ${cfg.border}`}
    >
      <div className="flex items-start gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border" style={{ borderColor: `${cfg.color}55`, background: `${cfg.color}12` }}>
          <Zap className="h-4.5 w-4.5" style={{ color: cfg.color }} strokeWidth={2.5} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.25em] text-ink-500">Today's Move</span>
            <span className="rounded px-1.5 py-0.5 font-mono text-[8.5px] font-black tracking-wide" style={{ color: cfg.color, background: `${cfg.color}1a` }}>{cfg.label}</span>
          </div>
          <div className="text-[15px] font-black leading-tight text-ink-100">{move.action}</div>
          {(move.target || move.counterparty) && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {move.target && <span className="rounded border border-ink-600 px-1.5 py-px font-mono text-[9px] text-ink-200">{move.target}</span>}
              {move.counterparty && (
                <span className="flex items-center gap-1 rounded border border-ink-600 px-1.5 py-px font-mono text-[9px] text-ink-200">
                  <Phone className="h-2.5 w-2.5" />{move.counterparty}
                </span>
              )}
            </div>
          )}
          <p className="mt-1.5 text-[11px] leading-relaxed text-ink-300">{move.rationale}</p>
          {quiet && move.ifQuiet && (
            <p className="mt-1 font-mono text-[10px] italic text-ink-500">{move.ifQuiet}</p>
          )}
        </div>
      </div>
    </motion.div>
  )
}

// ── proposed packages (deal sheets) ─────────────────────────────────────────────

function PkgSide({ title, players, color, align }: { title: string; players: PackagePlayer[]; color: string; align: 'left' | 'right' }) {
  return (
    <div className="flex-1">
      <div className={`mb-1 font-mono text-[8px] font-semibold uppercase tracking-[0.2em] ${align === 'right' ? 'text-right' : ''}`} style={{ color }}>{title}</div>
      <div className="space-y-1">
        {players.length === 0 && <div className="font-mono text-[10px] text-ink-600">—</div>}
        {players.map((p, i) => (
          <div key={i} className={`rounded border border-ink-700 bg-ink-900/50 px-2 py-1 ${align === 'right' ? 'text-right' : ''}`}>
            <div className="flex items-center gap-1.5" style={{ justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
              <span className="truncate font-mono text-[10.5px] font-semibold text-ink-100">{p.player}</span>
              <span className="font-mono text-[8px] text-ink-500">{p.position}</span>
            </div>
            <div className="font-mono text-[8.5px] text-ink-400">+{p.war3yr.toFixed(1)} WAR/3yr · +{p.surplusWar.toFixed(1)} sWAR</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ProposedPackages({ packages }: { packages: AnalysisReport['proposedPackages'] }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <SectionLabel sub="two-sided deal sheets · fairness-banded ±1.5 WAR">Proposed Packages</SectionLabel>
      <div className="space-y-3">
        {packages.map((pk, i) => {
          const ov = OVERPAY_CFG[pk.overpay]
          return (
            <motion.div
              key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
              className="rounded-lg border border-ink-700 bg-ink-950/40 p-3"
            >
              {/* header */}
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <TeamLogo team={pk.partner} size={20} />
                  <span className="font-mono text-[12px] font-bold text-ink-100">{pk.partner}</span>
                  <span className="font-mono text-[9px] font-semibold" style={{ color: POSTURE_COLOR[pk.partnerPosture] }}>{pk.partnerPosture.toUpperCase()}</span>
                </div>
                <span className="rounded px-1.5 py-0.5 font-mono text-[9px] font-black" style={{ color: ov.color, background: `${ov.color}1a` }}>{ov.label}</span>
              </div>
              {/* sides */}
              <div className="flex items-start gap-2">
                <PkgSide title="◀ You receive" players={pk.youReceive} color="#3ddc97" align="left" />
                <div className="grid shrink-0 place-items-center px-1 pt-4">
                  <ArrowLeftRight className="h-4 w-4 text-ink-600" />
                </div>
                <PkgSide title="You send ▶" players={pk.youSend} color="#ff8a3d" align="right" />
              </div>
              {/* balance + likelihood */}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-ink-700/50 pt-2">
                <span className="font-mono text-[9px] text-ink-500">
                  net <span className="font-bold" style={{ color: ov.color }}>{pk.netSurplusWar >= 0 ? '+' : ''}{pk.netSurplusWar.toFixed(1)} sWAR</span>
                </span>
                <span className="flex items-center gap-1 font-mono text-[9px] text-ink-500">
                  <DollarSign className="h-2.5 w-2.5" />${pk.dollarsToYouM.toFixed(1)}M in
                </span>
                <div className="flex items-center gap-1.5">
                  <div className="h-1 w-16 overflow-hidden rounded-full bg-ink-800">
                    <motion.div className="h-full rounded-full" style={{ background: pk.likelihood > 60 ? '#3ddc97' : pk.likelihood > 35 ? '#ff8a3d' : '#ff5d73' }}
                      initial={{ width: 0 }} animate={{ width: `${pk.likelihood}%` }} transition={{ duration: 0.7 }} />
                  </div>
                  <span className="font-mono text-[8.5px] text-ink-500">{pk.likelihood}% likely</span>
                </div>
              </div>
              {pk.framing && <p className="mt-1.5 text-[10.5px] italic leading-relaxed text-ink-300">“{pk.framing}”</p>}
              {(pk.likelihoodDrivers.length > 0 || pk.blockers.length > 0) && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {pk.likelihoodDrivers.map((d, j) => (
                    <span key={`d${j}`} className="rounded border border-positive-500/30 bg-positive-500/5 px-1 py-px font-mono text-[8px] text-positive-400">+ {d}</span>
                  ))}
                  {pk.blockers.map((b, j) => (
                    <span key={`b${j}`} className="rounded border border-negative-500/30 bg-negative-500/5 px-1 py-px font-mono text-[8px] text-negative-400">! {b}</span>
                  ))}
                </div>
              )}
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

// ── tiered target board ──────────────────────────────────────────────────────────

function TargetBoard({ board }: { board: AnalysisReport['targetBoard'] }) {
  const tiers: Tier[] = ['primary', 'fallback', 'dart-throw']
  const maxSurplus = Math.max(1, ...board.map(b => b.surplusWar))
  const positions = Array.from(new Set(board.map(b => b.position)))
  const [posFilter, setPosFilter] = useState<string>('all')
  const shown = posFilter === 'all' ? board : board.filter(b => b.position === posFilter)
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Target Board</span>
        <span className="font-mono text-[8.5px] text-ink-600">tiered · costed fallbacks ready</span>
        <div className="ml-auto flex flex-wrap gap-1">
          {['all', ...positions].map(p => (
            <button key={p} onClick={() => setPosFilter(p)}
              className={`rounded-full border px-2 py-0.5 font-mono text-[8.5px] uppercase tracking-wider transition-colors ${posFilter === p ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-500 hover:text-ink-300'}`}>
              {p}
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {tiers.map(tier => {
          const cards = shown.filter(b => b.tier === tier)
          const tc = TIER_CFG[tier]
          return (
            <div key={tier}>
              <div className="mb-1.5 flex items-center gap-1.5 border-b pb-1" style={{ borderColor: `${tc.color}40` }}>
                <span className="font-mono text-[9px] font-bold tracking-wide" style={{ color: tc.color }}>{tc.label}</span>
                <span className="font-mono text-[8px] text-ink-600">{cards.length}</span>
              </div>
              <div className="space-y-1.5">
                {cards.length === 0 && <div className="font-mono text-[9px] text-ink-700">—</div>}
                {cards.map((c, i) => {
                  const mot = MOTIVATION_CFG[c.sellerMotivation]
                  return (
                    <motion.div
                      key={i} initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.04 }}
                      className="rounded-lg border border-ink-700 bg-ink-950/40 p-2"
                      style={{ borderLeftColor: tc.color, borderLeftWidth: 2 }}
                    >
                      <div className="flex items-center gap-1.5">
                        <TeamLogo team={c.fromTeam} size={14} />
                        <span className="truncate text-[11px] font-semibold text-ink-100">{c.player}</span>
                        <span className="ml-auto rounded bg-ink-800 px-1 font-mono text-[8px] text-ink-400">{c.position}</span>
                      </div>
                      {/* surplus bar */}
                      <div className="mt-1 flex items-center gap-1">
                        <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-800">
                          <motion.div className="h-full rounded-full" style={{ background: tc.color }}
                            initial={{ width: 0 }} animate={{ width: `${(c.surplusWar / maxSurplus) * 100}%` }} transition={{ duration: 0.6 }} />
                        </div>
                        <span className="font-mono text-[8.5px] font-bold" style={{ color: tc.color }}>+{c.surplusWar.toFixed(1)}</span>
                      </div>
                      <div className="mt-0.5 font-mono text-[8px] text-ink-500">
                        {c.arbClass || '—'} · {c.controlYears}yr · ${c.yr1CostM.toFixed(1)}M
                      </div>
                      <div className="mt-1 flex items-center gap-1">
                        <span className="rounded px-1 font-mono text-[7.5px] font-bold" style={{ color: mot.color, background: `${mot.color}1a` }}>{mot.label}</span>
                        {c.healthFlag && (
                          <span className="flex items-center gap-0.5 rounded bg-negative-500/10 px-1 font-mono text-[7.5px] text-negative-400">
                            <AlertTriangle className="h-2 w-2" />{c.healthFlag}
                          </span>
                        )}
                      </div>
                      {c.likelyAsk && <div className="mt-1 text-[9px] leading-snug text-ink-500">ask: {c.likelyAsk}</div>}
                    </motion.div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── counterparty call order ──────────────────────────────────────────────────────

function CounterpartyCalls({ rows }: { rows: AnalysisReport['counterpartyLeverage'] }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <SectionLabel sub="who to call first · negative shift = their leverage weakening">Counterparty Call Order</SectionLabel>
      <div className="space-y-1.5">
        {rows.map((c, i) => {
          const weakening = c.leverageShift < 0
          const barColor = weakening ? '#3ddc97' : '#ff5d73'  // their weakness = your opportunity (green)
          const pct = Math.min(100, Math.abs(c.leverageShift))
          return (
            <motion.div key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
              className="flex items-center gap-2.5 rounded-lg border border-ink-700 bg-ink-950/40 px-2.5 py-1.5">
              <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full border border-accent-500/40 bg-accent-500/10 font-mono text-[9px] font-black text-accent-300">{c.callPriority}</span>
              <TeamLogo team={c.team} size={18} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[11px] font-bold text-ink-100">{c.team}</span>
                  <span className="font-mono text-[8px] font-semibold" style={{ color: POSTURE_COLOR[c.posture] }}>{c.posture.toUpperCase()}</span>
                  <span className="truncate font-mono text-[9px] text-ink-500">{c.trigger}</span>
                </div>
                {c.openWith && <div className="truncate text-[9.5px] text-ink-400">open: {c.openWith}</div>}
              </div>
              {/* diverging leverage bar */}
              <div className="flex w-20 shrink-0 items-center gap-1">
                <div className="relative h-1.5 flex-1 rounded-full bg-ink-800">
                  <motion.div className="absolute inset-y-0 rounded-full" style={{ background: barColor, [weakening ? 'right' : 'left']: '50%' }}
                    initial={{ width: 0 }} animate={{ width: `${pct / 2}%` }} transition={{ duration: 0.6 }} />
                  <div className="absolute inset-y-0 left-1/2 w-px bg-ink-600" />
                </div>
              </div>
            </motion.div>
          )
        })}
      </div>
    </div>
  )
}

// ── cap impact ────────────────────────────────────────────────────────────────

function CapImpact({ rows }: { rows: AnalysisReport['capImpact'] }) {
  const max = Math.max(1, ...rows.map(r => r.trueDollarCostM))
  const TIER_COLOR = ['#3ddc97', '#ff8a3d', '#ff6b3d', '#ff5d73']
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <SectionLabel sub="prorated true cost incl. CBT tax escalator">Cap Impact</SectionLabel>
      <div className="space-y-2">
        {rows.map((c, i) => {
          const taxOverlay = Math.max(0, c.trueDollarCostM - c.proratedRemainingM)
          return (
            <div key={i}>
              <div className="flex items-center justify-between font-mono text-[10px]">
                <span className="flex items-center gap-1.5 text-ink-200">
                  <Activity className="h-3 w-3 text-ink-500" />{c.player}
                  <span className="rounded px-1 text-[7.5px] font-bold" style={{ color: TIER_COLOR[c.tierAfter], background: `${TIER_COLOR[c.tierAfter]}1a` }}>T{c.tierAfter}</span>
                </span>
                <span className="text-ink-300">${c.trueDollarCostM.toFixed(1)}M true</span>
              </div>
              <div className="mt-0.5 flex h-2 overflow-hidden rounded-full bg-ink-800">
                <motion.div className="h-full bg-ink-500" initial={{ width: 0 }} animate={{ width: `${(c.proratedRemainingM / max) * 100}%` }} transition={{ duration: 0.6 }} />
                <motion.div className="h-full" style={{ background: TIER_COLOR[c.tierAfter] }} initial={{ width: 0 }} animate={{ width: `${(taxOverlay / max) * 100}%` }} transition={{ duration: 0.6, delay: 0.2 }} />
              </div>
              {c.note && <div className="mt-0.5 font-mono text-[8px] text-ink-600">{c.note}</div>}
            </div>
          )
        })}
      </div>
      <div className="mt-2 flex gap-3">
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-ink-500" /><span className="font-mono text-[8px] text-ink-500">prorated salary</span></div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-accent-500" /><span className="font-mono text-[8px] text-ink-500">CBT tax</span></div>
      </div>
    </div>
  )
}

// ── matrix tooltip ────────────────────────────────────────────────────────────

function MatrixTooltip({ active, payload }: { active?: boolean; payload?: { payload: AnalysisReport['priorityMatrix'][number] }[] }) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="rounded border border-ink-700 bg-ink-900 p-2 text-[10px]">
      <div className="font-mono font-semibold text-ink-100">{p.label}</div>
      <div className="font-mono text-ink-400">{CATEGORY_CFG[p.category].label}</div>
      <div className="mt-1 font-mono text-ink-300">${p.costM.toFixed(1)}M · {p.impactWar >= 0 ? '+' : ''}{p.impactWar.toFixed(1)} WAR</div>
      <div className="font-mono text-ink-500">{p.feasibility}% feasible</div>
    </div>
  )
}

// ── KPI strip + section nav ──────────────────────────────────────────────────

function KpiTile({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2">
      <div className="font-mono text-[8px] font-semibold uppercase tracking-[0.18em] text-ink-500">{label}</div>
      <div className="font-mono text-[18px] font-black leading-none tabular" style={{ color: color ?? '#e6ebff' }}>{value}</div>
      {sub && <div className="mt-0.5 font-mono text-[8px] text-ink-600">{sub}</div>}
    </div>
  )
}

function KpiStrip({ report }: { report: AnalysisReport }) {
  const pkgs = report.proposedPackages
  const bestNet = pkgs.length ? Math.max(...pkgs.map(p => p.netSurplusWar)) : 0
  const primaries = report.targetBoard.filter(t => t.tier === 'primary').length
  const topCall = report.counterpartyLeverage[0]?.team ?? '—'
  const mat = report.todaysMove?.materiality ?? 'quiet'
  const matColor = mat === 'urgent' ? '#ff5d73' : mat === 'notable' ? '#ff8a3d' : '#8a96c0'
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      <KpiTile label="Today" value={mat.toUpperCase()} color={matColor} sub="materiality" />
      <KpiTile label="Packages" value={String(pkgs.length)} sub="ready to pitch" />
      <KpiTile label="Best net" value={`${bestNet >= 0 ? '+' : ''}${bestNet.toFixed(1)}`} sub="sWAR swing" color={bestNet >= 0 ? '#3ddc97' : '#ff5d73'} />
      <KpiTile label="Primary tgts" value={String(primaries)} sub="on the board" />
      <KpiTile label="First call" value={topCall} sub="counterparty" color="#ff8a3d" />
    </div>
  )
}

function SectionNav({ items }: { items: { id: string; label: string }[] }) {
  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  return (
    <div className="sticky top-0 z-10 -mx-1 flex flex-wrap gap-1 bg-ink-950/85 px-1 py-1.5 backdrop-blur">
      {items.map(it => (
        <button key={it.id} onClick={() => jump(it.id)}
          className="rounded-full border border-ink-700 px-2.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-ink-400 transition-colors hover:border-accent-500/50 hover:text-accent-300">
          {it.label}
        </button>
      ))}
    </div>
  )
}

// ── main ───────────────────────────────────────────────────────────────────────

export function IntelligenceReport({ report }: { report: AnalysisReport }) {
  const v = VERDICT_CFG[report.verdict]
  const navItems = ([
    report.todaysMove ? { id: 'brief-move', label: 'Move' } : null,
    report.keyFindings.length ? { id: 'brief-findings', label: 'Findings' } : null,
    report.proposedPackages.length ? { id: 'brief-packages', label: 'Packages' } : null,
    report.targetBoard.length ? { id: 'brief-board', label: 'Board' } : null,
    report.counterpartyLeverage.length ? { id: 'brief-calls', label: 'Calls' } : null,
    { id: 'brief-outlook', label: 'Outlook' },
  ].filter(Boolean)) as { id: string; label: string }[]

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      {/* Verdict header */}
      <div className={`rounded-lg border p-4 ${v.bg} ${v.border}`}>
        <div className="flex items-start gap-4">
          <ConfidenceRing value={report.confidence} color={v.color} />
          <div className="min-w-0 flex-1">
            <div className="mb-1 flex items-center gap-2">
              <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.25em] text-ink-500">Brief verdict</span>
              <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-black tracking-wide" style={{ color: v.color, background: `${v.color}1a` }}>{v.label}</span>
            </div>
            <h3 className="display text-[18px] font-black leading-tight text-ink-100">{report.headline}</h3>
            {report.executiveSummary && <p className="mt-1.5 text-[12px] leading-relaxed text-ink-300">{report.executiveSummary}</p>}
          </div>
        </div>
      </div>

      {/* KPI strip + section nav */}
      <KpiStrip report={report} />
      <SectionNav items={navItems} />

      {/* Today's move */}
      {report.todaysMove && (
        <section id="brief-move" style={{ scrollMarginTop: 56 }}>
          <TodaysMove move={report.todaysMove} />
        </section>
      )}

      {/* Key findings */}
      {report.keyFindings.length > 0 && (
        <div id="brief-findings" style={{ scrollMarginTop: 56 }} className="grid gap-2 sm:grid-cols-2">
          {report.keyFindings.map((f, i) => {
            const cfg = FINDING_CFG[f.kind]; const Icon = cfg.Icon
            return (
              <motion.div key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                className={`rounded-lg border border-ink-700 p-3 ${cfg.bg}`} style={{ borderLeftColor: cfg.color, borderLeftWidth: 2 }}>
                <div className="flex items-center gap-1.5">
                  <Icon className="h-3.5 w-3.5" style={{ color: cfg.color }} />
                  <span className="text-[12px] font-semibold text-ink-100">{f.title}</span>
                </div>
                <p className="mt-1 text-[11px] leading-relaxed text-ink-400">{f.detail}</p>
              </motion.div>
            )
          })}
        </div>
      )}

      {/* Proposed packages — the headline feature */}
      {report.proposedPackages.length > 0 && (
        <section id="brief-packages" style={{ scrollMarginTop: 56 }}>
          <ProposedPackages packages={report.proposedPackages} />
        </section>
      )}

      {/* Target board */}
      {report.targetBoard.length > 0 && (
        <section id="brief-board" style={{ scrollMarginTop: 56 }}>
          <TargetBoard board={report.targetBoard} />
        </section>
      )}

      {/* Recommendations */}
      {report.recommendations.length > 0 && (
        <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
          <SectionLabel>Prioritized recommendations</SectionLabel>
          <div className="space-y-2.5">
            {report.recommendations.map((r, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                className="flex gap-3 rounded-lg border border-ink-700 bg-ink-900/40 p-3">
                <div className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-accent-500/40 bg-accent-500/10 font-mono text-[11px] font-black text-accent-300">{r.rank}</div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[13px] font-semibold text-ink-100">{r.action}</span>
                    <span className="flex items-center gap-0.5 rounded bg-ink-800 px-1 py-px font-mono text-[8px] font-bold text-ink-400"><Clock className="h-2.5 w-2.5" />{HORIZON_LABEL[r.horizon]}</span>
                    <span className={`font-mono text-[10px] font-bold ${r.impactWar >= 0 ? 'text-positive-400' : 'text-negative-400'}`}>{r.impactWar >= 0 ? '+' : ''}{r.impactWar.toFixed(1)} WAR</span>
                  </div>
                  <p className="mt-0.5 text-[11px] leading-relaxed text-ink-400">{r.rationale}</p>
                  {r.targets.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {r.targets.map(t => <span key={t} className="rounded border border-ink-600 px-1.5 py-px font-mono text-[9px] text-ink-300">{t}</span>)}
                    </div>
                  )}
                  <div className="mt-1.5 flex items-center gap-2">
                    <div className="h-1 flex-1 overflow-hidden rounded-full bg-ink-800">
                      <motion.div className="h-full rounded-full bg-accent-400" initial={{ width: 0 }} animate={{ width: `${r.confidence}%` }} transition={{ duration: 0.8, delay: i * 0.06 }} />
                    </div>
                    <span className="font-mono text-[8.5px] text-ink-500">{r.confidence}% conf</span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* Counterparty call order */}
      {report.counterpartyLeverage.length > 0 && (
        <section id="brief-calls" style={{ scrollMarginTop: 56 }}>
          <CounterpartyCalls rows={report.counterpartyLeverage} />
        </section>
      )}

      {/* Charts grid */}
      <div id="brief-outlook" style={{ scrollMarginTop: 56 }} className="grid gap-4 lg:grid-cols-2">
        {report.priorityMatrix.length > 0 && (
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
            <SectionLabel sub="cost ($M) × impact (WAR) · bubble = feasibility">Priority Matrix</SectionLabel>
            <ResponsiveContainer width="100%" height={220}>
              <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: -8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2238" />
                <XAxis type="number" dataKey="costM" tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }} tickFormatter={(x: number) => `$${x}M`} axisLine={false} tickLine={false} />
                <YAxis type="number" dataKey="impactWar" tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }} tickFormatter={(x: number) => `${x}W`} axisLine={false} tickLine={false} />
                <ZAxis type="number" dataKey="feasibility" range={[40, 320]} />
                <ReferenceLine y={0} stroke="#364264" />
                <Tooltip content={<MatrixTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                <Scatter data={report.priorityMatrix}>
                  {report.priorityMatrix.map((m, i) => <Cell key={i} fill={CATEGORY_CFG[m.category].color} fillOpacity={0.65} />)}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
            <div className="mt-1 flex flex-wrap gap-3">
              {(Object.keys(CATEGORY_CFG) as MatrixCategory[]).map(c => (
                <div key={c} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: CATEGORY_CFG[c].color }} /><span className="font-mono text-[8px] text-ink-500">{CATEGORY_CFG[c].label}</span></div>
              ))}
            </div>
          </div>
        )}

        {report.riskRadar.length >= 3 && (
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
            <SectionLabel sub="100 = healthy · 0 = severe weakness">Org Risk Profile</SectionLabel>
            <ResponsiveContainer width="100%" height={220}>
              <RadarChart data={report.riskRadar} margin={{ top: 10, right: 24, bottom: 10, left: 24 }}>
                <PolarGrid stroke="#1a2238" />
                <PolarAngleAxis dataKey="axis" tick={{ fill: '#8a96c0', fontSize: 8.5, fontFamily: 'JetBrains Mono' }} />
                <Radar dataKey="score" stroke="#ff8a3d" fill="#ff8a3d" fillOpacity={0.18} strokeWidth={1.5} dot={{ r: 2.5, fill: '#ff8a3d', strokeWidth: 0 }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        )}

        {report.winProjection.length > 0 && (
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
            <SectionLabel sub="floor / expected / ceiling · wins per season">Win Projection</SectionLabel>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={report.winProjection} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <defs>
                  <linearGradient id="ceilGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3ddc97" stopOpacity={0.3} /><stop offset="100%" stopColor="#3ddc97" stopOpacity={0.02} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2238" vertical={false} />
                <XAxis dataKey="year" tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} domain={['dataMin - 5', 'dataMax + 5']} />
                <Tooltip contentStyle={{ background: '#0d1117', border: '1px solid #1a2238', borderRadius: 6, fontSize: 10, fontFamily: 'JetBrains Mono' }} labelStyle={{ color: '#cdd5f0' }} />
                <ReferenceLine y={88} stroke="#ff8a3d" strokeDasharray="4 2" label={{ value: 'playoff line ~88', fill: '#ff8a3d', fontSize: 8, position: 'insideTopLeft' }} />
                <Area type="monotone" dataKey="ceiling" stroke="#3ddc97" strokeWidth={1} fill="url(#ceilGrad)" />
                <Area type="monotone" dataKey="expected" stroke="#5b9dff" strokeWidth={2} fill="none" />
                <Area type="monotone" dataKey="floor" stroke="#ff5d73" strokeWidth={1} strokeDasharray="3 3" fill="none" />
              </AreaChart>
            </ResponsiveContainer>
            <div className="mt-1 flex gap-3">
              {[['#3ddc97', 'Ceiling'], ['#5b9dff', 'Expected'], ['#ff5d73', 'Floor']].map(([c, l]) => (
                <div key={l} className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: c }} /><span className="font-mono text-[8px] text-ink-500">{l}</span></div>
              ))}
            </div>
          </div>
        )}

        {report.contentionTimeline.length > 0 && (
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
            <SectionLabel sub="projected competitiveness 0-100">Contention Timeline</SectionLabel>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={report.contentionTimeline} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                <defs>
                  <linearGradient id="contGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#ff6a13" stopOpacity={0.35} /><stop offset="100%" stopColor="#ff6a13" stopOpacity={0.02} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2238" vertical={false} />
                <XAxis dataKey="year" tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#8a96c0', fontSize: 9, fontFamily: 'JetBrains Mono' }} axisLine={false} tickLine={false} domain={[0, 100]} />
                <Tooltip contentStyle={{ background: '#0d1117', border: '1px solid #1a2238', borderRadius: 6, fontSize: 10, fontFamily: 'JetBrains Mono' }} labelStyle={{ color: '#cdd5f0' }}
                  formatter={(val, _n, item) => { const note = (item?.payload as { note?: string })?.note; return [`${val}${note ? ` — ${note}` : ''}`, 'competitiveness'] }} />
                <Area type="monotone" dataKey="competitiveness" stroke="#ff6a13" strokeWidth={2} fill="url(#contGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Cap impact (full width) */}
      {report.capImpact.length > 0 && <CapImpact rows={report.capImpact} />}

      {report.generatedAt && (
        <div className="text-right font-mono text-[8.5px] text-ink-700">rendered {new Date(report.generatedAt).toLocaleString()}</div>
      )}
    </motion.div>
  )
}
