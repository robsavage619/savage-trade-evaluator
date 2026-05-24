import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence, animate } from 'framer-motion'
import {
  TrendingUp, TrendingDown, Minus, Info, Sparkles, Target,
  ArrowLeftRight, Trash2, X, BadgePlus, ChevronRight, Radio,
  Brain, ClipboardCopy, ClipboardCheck, Check, RefreshCw, FileText,
  Settings, KeyRound, Maximize2, Loader2, Wand2,
} from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine, Cell,
} from 'recharts'
import { useIdentityStore } from '../lib/identityStore'
import { warRoomIndex, loadTeamPayload, loadAllTeamPayloads } from '../lib/warroomData'
import type { Citation, HoleEntry, TeamPayload, WindowPosture } from '../data/warroom/types'
import { TeamLogo } from '../components/TeamLogo'
import { PlayerPicker, BasketCard } from '../components/PlayerPicker'
import { Stat } from '../components/Section'
import { forecastArb, isControlled, parseArbClass } from '../lib/arbForecast'
import type { ArbClass } from '../lib/arbForecast'
import { computeVerdict, DEV_SIGNATURE, MARKET_RATE, fvToWar, agingDelta } from '../lib/hypothetical'
import type { ProspectEntry, VerdictContext } from '../lib/hypothetical'
import type { CurrentPlayer } from '../data/players'
import { useRoster, useTeamsByBref } from '../lib/rosterStore'
import { fmtMoney } from '../lib/format'
import { computeDeals } from '../lib/dealsEngine'
import { computeBuyLow } from '../lib/buyLowEngine'
import type { DealCandidate } from '../lib/dealsEngine'
import type { BuyLowCandidate } from '../lib/buyLowEngine'
import { buildAnalysisPrompt, parseAnalysisReport } from '../lib/analysisPrompt'
import type { AnalysisReport, PromptInput } from '../lib/analysisPrompt'
import { generateBriefRaw } from '../lib/analysisClient'
import { IntelligenceReport } from '../components/IntelligenceReport'

// ── posture config ───────────────────────────────────────────────────────────

const POSTURE: Record<WindowPosture, {
  label: string
  color: string
  glow: string
  bg: string
  border: string
  dot: string
  Icon: typeof TrendingUp
}> = {
  buy: {
    label: 'BUY WINDOW',
    color: 'text-positive-500',
    glow: 'shadow-[0_0_24px_rgba(61,220,151,0.25)]',
    bg: 'bg-positive-500/[0.07]',
    border: 'border-positive-500/30',
    dot: 'bg-positive-500',
    Icon: TrendingUp,
  },
  sell: {
    label: 'SELL MODE',
    color: 'text-negative-500',
    glow: 'shadow-[0_0_24px_rgba(255,93,115,0.2)]',
    bg: 'bg-negative-500/[0.07]',
    border: 'border-negative-500/30',
    dot: 'bg-negative-500',
    Icon: TrendingDown,
  },
  hold: {
    label: 'HOLD / ASSESS',
    color: 'text-accent-400',
    glow: 'shadow-[0_0_24px_rgba(255,106,19,0.15)]',
    bg: 'bg-accent-500/[0.07]',
    border: 'border-accent-500/30',
    dot: 'bg-accent-400',
    Icon: Minus,
  },
}

const SEVERITY_COLOR: Record<string, string> = {
  critical: '#ff5d73',
  warning: '#ff8a3d',
  ok: '#364264',
}

const DIVISIONS = ['AL East', 'AL Central', 'AL West', 'NL East', 'NL Central', 'NL West']

// ── helpers ──────────────────────────────────────────────────────────────────

function money(v: number) {
  const neg = v < 0; const a = Math.abs(v)
  const s = a >= 1_000_000 ? `$${(a / 1_000_000).toFixed(1)}M` : `$${(a / 1_000).toFixed(0)}K`
  return neg ? `−${s}` : s
}

function Cite({ cite }: { cite: Citation }) {
  return (
    <span className="group relative inline-flex cursor-help">
      <Info className="h-3 w-3 text-ink-600 hover:text-accent-400 transition-colors" />
      <span className="pointer-events-none absolute bottom-[calc(100%+6px)] left-1/2 z-50 hidden w-72 -translate-x-1/2 rounded-lg border border-ink-600 bg-ink-900 p-3 text-left text-[10px] leading-relaxed text-ink-300 shadow-2xl group-hover:block">
        <span className="font-mono font-semibold uppercase tracking-wider text-accent-300 text-[9px]">{cite.label}</span>
        <div className="mt-1 text-ink-300">{cite.detail}</div>
      </span>
    </span>
  )
}

// ── section header ────────────────────────────────────────────────────────────

function SectionHeader({ label, cite }: { label: string; cite?: Citation }) {
  return (
    <div className="flex items-center gap-3">
      <div className="h-3.5 w-[3px] rounded-full bg-accent-500/70 shrink-0" />
      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.25em] text-ink-300">{label}</span>
      {cite && <Cite cite={cite} />}
      <div className="flex-1 h-px bg-ink-800" />
    </div>
  )
}

// ── animated number ──────────────────────────────────────────────────────────

function AnimatedNumber({
  end, duration = 1.2, decimals = 0, prefix = '', suffix = '', separator = '',
}: { end: number; duration?: number; decimals?: number; prefix?: string; suffix?: string; separator?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  useEffect(() => {
    const controls = animate(0, end, {
      duration,
      ease: 'easeOut',
      onUpdate(v) {
        if (!ref.current) return
        let s = v.toFixed(decimals)
        if (separator) {
          const parts = s.split('.')
          parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, separator)
          s = parts.join('.')
        }
        ref.current.textContent = prefix + s + suffix
      },
    })
    return () => controls.stop()
  }, [end, duration, decimals, prefix, suffix, separator])
  return (
    <span ref={ref}>
      {prefix}{end.toFixed(decimals)}{suffix}
    </span>
  )
}

// ── pulsing status dot ───────────────────────────────────────────────────────

function PulseDot({ color }: { color: string }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${color}`} />
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
    </span>
  )
}

// ── playoff probability ───────────────────────────────────────────────────────

/** Logistic heuristic — 12/30 teams make playoffs; adjusted for win% and games back. */
function computePlayoffProb(w: number, l: number, gamesBack: number): number {
  const total = w + l
  if (total === 0) return 0.4
  const winPct = w / total
  const logit = (winPct - 0.5) * 12 - gamesBack * 0.12 - 0.25
  return Math.max(0.02, Math.min(0.97, 1 / (1 + Math.exp(-logit))))
}

// ── posture banner ───────────────────────────────────────────────────────────

function PostureBanner({ posture, rationale, playoffProb, w, l, gamesBack }: {
  posture: WindowPosture
  rationale: string
  playoffProb: number
  w: number
  l: number
  gamesBack: number
}) {
  const cfg = POSTURE[posture]
  const Icon = cfg.Icon
  const probColor = playoffProb > 0.65 ? 'text-positive-400' : playoffProb > 0.35 ? 'text-accent-300' : 'text-negative-400'
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative overflow-hidden rounded-lg border p-5 ${cfg.bg} ${cfg.border} ${cfg.glow}`}
    >
      {/* corner brackets */}
      <span className={`absolute left-2 top-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>┌─</span>
      <span className={`absolute right-2 top-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>─┐</span>
      <span className={`absolute bottom-2 left-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>└─</span>
      <span className={`absolute bottom-2 right-2 text-[10px] font-mono opacity-40 ${cfg.color}`}>─┘</span>
      <div className="flex items-start gap-5">
        {/* Icon */}
        <div className={`grid h-16 w-16 shrink-0 place-items-center rounded-xl border-2 ${cfg.border} ${cfg.bg}`}>
          <Icon className={`h-8 w-8 ${cfg.color}`} strokeWidth={2.5} />
        </div>

        {/* Main content */}
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex items-center gap-2">
            <PulseDot color={cfg.dot} />
            <span className={`font-mono text-[9px] font-semibold uppercase tracking-[0.3em] ${cfg.color} opacity-80`}>
              WINDOW ASSESSMENT
            </span>
            <Cite cite={{ label: 'Window Posture', detail: 'Derived from W-L record, division gap, games back, and payroll flexibility. Buy = contention-window team with room to add; Sell = out of contention; Hold = ambiguous.' }} />
          </div>
          <div className={`display text-[38px] font-black leading-none tracking-tight ${cfg.color}`}>
            {cfg.label}
          </div>
          <p className="mt-2 max-w-xl text-[11px] leading-relaxed text-ink-300">{rationale}</p>

          {/* Record strip */}
          <div className="mt-3 flex items-center gap-5">
            <div className="flex items-baseline gap-1.5">
              <span className="font-mono text-[22px] font-black leading-none text-ink-100 tabular">{w}–{l}</span>
              <span className="font-mono text-[10px] text-ink-500">W-L</span>
            </div>
            <div className="h-6 w-px bg-ink-700" />
            <div className="flex items-baseline gap-1">
              <span className={`font-mono text-[18px] font-black leading-none tabular ${gamesBack === 0 ? 'text-positive-400' : gamesBack > 8 ? 'text-negative-400' : 'text-ink-200'}`}>
                {gamesBack === 0 ? '—' : gamesBack}
              </span>
              <span className="font-mono text-[10px] text-ink-500">{gamesBack === 0 ? 'DIV LEAD' : 'GB'}</span>
            </div>
            <div className="h-6 w-px bg-ink-700" />
            <div className="flex items-baseline gap-1">
              <span className={`font-mono text-[18px] font-black leading-none tabular ${probColor}`}>
                {Math.round(playoffProb * 100)}%
              </span>
              <span className="font-mono text-[9px] text-ink-500 flex items-center gap-0.5">
                P(PLAYOFF)
                <Cite cite={{ label: 'Playoff Probability', detail: 'Logistic model: win%, games back, games remaining. 12 of 30 teams qualify. Not market-implied — heuristic only.' }} />
              </span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  )
}

// ── payroll gauge ────────────────────────────────────────────────────────────

const CBT_TIERS = [
  { label: 'T1', offset: 0,          rate: '20%',   color: '#ff8a3d' },
  { label: 'T2', offset: 20_000_000, rate: '32%',   color: '#ff6b3d' },
  { label: 'T3', offset: 40_000_000, rate: '62.5%', color: '#ff5d73' },
]

function PayrollGauge({ committed, threshold, headroom }: { committed: number; threshold: number; headroom: number }) {
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

// ── position radar ────────────────────────────────────────────────────────────

function PositionRadar({ holes, surpluses, posture }: { holes: HoleEntry[]; surpluses: HoleEntry[]; posture: WindowPosture }) {
  const cfg = POSTURE[posture]

  const data = useMemo(() => {
    const allPositions = [...new Set([...holes, ...surpluses].map(h => h.position))]
    return allPositions.map(pos => {
      const hole = holes.find(h => h.position === pos)
      const surplus = surpluses.find(h => h.position === pos)
      // 0 = critical gap, 50 = replacement level, 100 = major surplus
      const score = hole
        ? Math.max(0, 50 - (hole.holeScore / hole.replacementBaseline) * 50)
        : surplus
        ? Math.min(100, 50 + ((surplus.surplus ?? 0) / surplus.replacementBaseline) * 50)
        : 50
      return { position: pos, value: Math.round(score) }
    })
  }, [holes, surpluses])

  if (data.length < 3) return null

  const radarColor = posture === 'buy' ? '#3ddc97' : posture === 'sell' ? '#ff5d73' : '#ff8a3d'

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Position Shape</span>
        <Cite cite={{ label: 'Position Shape Radar', detail: '0 = critical gap (well below replacement) · 50 = replacement level · 100 = tradeable surplus. Shape shows where your roster over- and under-produces relative to league baseline.' }} />
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <RadarChart data={data} margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
          <PolarGrid stroke="#1a2238" />
          <PolarAngleAxis
            dataKey="position"
            tick={{ fill: '#8a96c0', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          />
          <Radar
            dataKey="value"
            stroke={radarColor}
            fill={radarColor}
            fillOpacity={0.15}
            strokeWidth={1.5}
            dot={{ r: 2.5, fill: radarColor, strokeWidth: 0 }}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── holes board ──────────────────────────────────────────────────────────────

const HOLE_SCORE_CITE: Citation = {
  label: 'Hole Score',
  detail: 'WAR deficit vs a replacement-level player at this position. −2.2 = this slot is costing you ~2 wins. Critical = needs an upgrade at the deadline.',
}
const SURPLUS_WAR_CITE: Citation = {
  label: 'Tradeable Surplus',
  detail: 'WAR production above salary cost over remaining control years. Positive surplus = cost-controlled asset. This is the currency of any trade.',
}

function HolesBoard({ holes, surpluses }: { holes: HoleEntry[]; surpluses: HoleEntry[] }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      {holes.length > 0 && (
        <div className="mb-4">
          <div className="mb-2.5 flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-negative-400">▼ Needs</span>
            <Cite cite={HOLE_SCORE_CITE} />
          </div>
          <div className="space-y-2">
            {holes.map((h, i) => (
              <motion.div
                key={h.position}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center gap-3"
                style={{ borderLeft: `3px solid ${SEVERITY_COLOR[h.severity]}` }}
              >
                <span className="font-mono w-8 shrink-0 pl-2.5 text-[12px] font-bold text-ink-100">{h.position}</span>
                <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-ink-800">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (h.holeScore / h.replacementBaseline) * 100)}%` }}
                    transition={{ duration: 0.8, delay: i * 0.05, ease: 'easeOut' }}
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{ background: SEVERITY_COLOR[h.severity], boxShadow: `0 0 8px ${SEVERITY_COLOR[h.severity]}60` }}
                  />
                </div>
                <div className="shrink-0 flex items-center gap-1.5">
                  <span className="font-mono text-[15px] font-black leading-none tabular text-negative-400">
                    −{h.holeScore.toFixed(1)}
                  </span>
                  {h.severity === 'critical' && (
                    <span className="rounded bg-negative-500/15 px-1 py-px font-mono text-[8px] font-bold uppercase tracking-wider text-negative-400">CRIT</span>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      )}
      {surpluses.length > 0 && (
        <div>
          <div className="mb-2.5 flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-positive-400">▲ Tradeable surplus</span>
            <Cite cite={SURPLUS_WAR_CITE} />
          </div>
          <div className="space-y-2">
            {surpluses.map((h, i) => (
              <motion.div
                key={h.position}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 + 0.15 }}
                className="flex items-center gap-3 border-l-[3px] border-positive-500/50"
              >
                <span className="font-mono w-8 shrink-0 pl-2.5 text-[12px] font-bold text-ink-100">{h.position}</span>
                <div className="relative flex-1 h-2 overflow-hidden rounded-full bg-ink-800">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, ((h.surplus ?? 0) / h.replacementBaseline) * 100)}%` }}
                    transition={{ duration: 0.8, delay: i * 0.05 + 0.15, ease: 'easeOut' }}
                    className="absolute inset-y-0 left-0 rounded-full bg-positive-500/70"
                    style={{ boxShadow: '0 0 8px rgba(61,220,151,0.4)' }}
                  />
                </div>
                <span className="font-mono shrink-0 text-[15px] font-black leading-none tabular text-positive-400">
                  +{(h.surplus ?? 0).toFixed(1)}
                </span>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── league ticker ─────────────────────────────────────────────────────────────

function LeagueTicker({ yourBref, partnerBref, onSelect }: {
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

// ── partner panel ─────────────────────────────────────────────────────────────

function PartnerPanel({ bref, payload, onClose }: {
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
        <div className="py-6 text-center font-mono text-[11px] text-ink-600">Loading {bref} intel…</div>
      )}
    </motion.div>
  )
}

// ── prospect adder ─────────────────────────────────────────────────────────────

const FV_OPTIONS = [80, 70, 60, 55, 50, 45, 40] as const

function ProspectAdder({ onAdd }: { onAdd: (p: ProspectEntry) => void }) {
  const [name, setName] = useState('')
  const [fv, setFv] = useState<ProspectEntry['fvGrade']>(50)
  return (
    <div className="mt-1.5 flex gap-1">
      <input
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && name.trim()) { onAdd({ name: name.trim(), fvGrade: fv }); setName('') } }}
        placeholder="Prospect name…"
        className="min-w-0 flex-1 rounded border border-ink-700 bg-ink-800/60 px-2 py-1 text-[11px] text-ink-100 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
      />
      <select
        value={fv}
        onChange={e => setFv(Number(e.target.value) as ProspectEntry['fvGrade'])}
        className="rounded border border-ink-700 bg-ink-800 px-1.5 py-1 text-[11px] text-ink-200 focus:outline-none"
      >
        {FV_OPTIONS.map(v => <option key={v} value={v}>{v} FV (~{fvToWar(v).toFixed(1)} WAR)</option>)}
      </select>
      <button
        onClick={() => { if (name.trim()) { onAdd({ name: name.trim(), fvGrade: fv }); setName('') } }}
        className="rounded border border-accent-500/40 bg-accent-500/10 px-2 py-1 font-mono text-[10px] text-accent-300 transition-colors hover:bg-accent-500/20"
      >
        +
      </button>
    </div>
  )
}

// ── trade workshop ─────────────────────────────────────────────────────────────

function TradeWorkshop({ yourBref, partnerBref, verdictCtx }: {
  yourBref: string
  partnerBref: string
  verdictCtx: VerdictContext
}) {
  const teamsByBref = useTeamsByBref()
  const yourTeam = teamsByBref[yourBref]
  const partnerTeam = teamsByBref[partnerBref]
  const [sentIds, setSentIds] = useState<number[]>([])
  const [receivedIds, setReceivedIds] = useState<number[]>([])
  const [sentProspects, setSentProspects] = useState<ProspectEntry[]>([])
  const [receivedProspects, setReceivedProspects] = useState<ProspectEntry[]>([])

  useEffect(() => {
    setSentIds([]); setReceivedIds([])
    setSentProspects([]); setReceivedProspects([])
  }, [partnerBref])

  const sendingPlayers = useMemo(
    () => sentIds.map(id => yourTeam?.players.find(p => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [sentIds, yourTeam],
  )
  const receivingPlayers = useMemo(
    () => receivedIds.map(id => partnerTeam?.players.find(p => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [receivedIds, partnerTeam],
  )

  const verdict = useMemo(
    () => yourTeam && partnerTeam
      ? computeVerdict(
          {
            sending: { team: yourTeam, players: sendingPlayers, prospects: sentProspects },
            receiving: { team: partnerTeam, players: receivingPlayers, prospects: receivedProspects },
          },
          verdictCtx,
        )
      : null,
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers, sentProspects, receivedProspects, verdictCtx],
  )

  const receivedArbTotal = useMemo(() =>
    receivingPlayers.reduce((acc, p) => {
      const a = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
      return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
    }, 0), [receivingPlayers],
  )
  const sentArbTotal = useMemo(() =>
    sendingPlayers.reduce((acc, p) => {
      const a = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
      return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
    }, 0), [sendingPlayers],
  )

  if (!yourTeam || !partnerTeam) return null

  const { currentW = 0, currentL = 0, gamesBack = 0, playoffProb = 0.4 } = verdictCtx as {
    currentW?: number; currentL?: number; gamesBack?: number; playoffProb?: number
  }
  const salaryDelta = (verdict?.costReceived ?? 0) - (verdict?.costSent ?? 0)
  const rec = verdict?.recommendation
  const recBorder = rec === 'strong-buy' || rec === 'lean-buy'
    ? 'border-positive-500/30 bg-positive-500/5'
    : rec === 'strong-pass' || rec === 'lean-pass'
    ? 'border-negative-500/30 bg-negative-500/5'
    : 'border-ink-700 bg-ink-800/40'
  const dollarColor = (verdict?.netValueDollars ?? 0) >= 0 ? 'text-positive-400' : 'text-negative-400'

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-4 rounded-lg border border-ink-700 bg-ink-900/80 p-4"
      style={{ boxShadow: '0 0 40px rgba(0,0,0,0.4) inset' }}
    >
      {/* Header bar */}
      <div className="mb-4 flex items-center justify-between border-b border-ink-700 pb-3">
        <div className="flex items-center gap-2.5">
          <Radio className="h-3.5 w-3.5 text-accent-400" />
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-300">
            Trade Workshop
          </span>
          <span className="font-mono text-[10px] text-ink-400">
            {yourBref} <ArrowLeftRight className="inline h-2.5 w-2.5" /> {partnerBref}
          </span>
        </div>
        <button
          onClick={() => { setSentIds([]); setReceivedIds([]); setSentProspects([]); setReceivedProspects([]) }}
          className="flex items-center gap-1 font-mono text-[9px] text-ink-600 transition-colors hover:text-negative-400"
        >
          <Trash2 className="h-3 w-3" /> CLEAR
        </button>
      </div>

      {/* Verdict */}
      {verdict ? (
        <div className={`mb-4 rounded-lg border p-4 ${recBorder}`}>
          <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">
            GM Decision Signal
          </div>
          {/* Primary: single dollar value */}
          <div className="mb-3 flex items-end gap-4">
            <div>
              <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">Net surplus value</div>
              <div className={`font-mono text-[40px] font-black leading-none tabular ${dollarColor}`}>
                {(verdict.netValueDollars >= 0 ? '+' : '−')}
                <AnimatedNumber
                  end={Math.abs(verdict.netValueDollars) / 1_000_000}
                  decimals={1}
                  prefix="$"
                  suffix="M"
                />
              </div>
              <div className="mt-0.5 font-mono text-[10px] text-ink-400">
                {verdict.surplusMean >= 0 ? '+' : ''}{verdict.surplusMean.toFixed(1)} WAR 3yr ·
                P(+) <span className={dollarColor}>{Math.round(verdict.pPositive * 100)}%</span> ·
                {' '}{verdict.recommendationLabel}
              </div>
            </div>
          </div>
          {/* Secondary decomposition */}
          <div className="flex flex-wrap gap-4 border-t border-ink-700/40 pt-2.5">
            <Stat label="WAR Δ (3yr)" value={`${(verdict.warReceived - verdict.warSent) >= 0 ? '+' : ''}${(verdict.warReceived - verdict.warSent).toFixed(1)}`} sub="aging + dev adjusted" tone={verdict.reasoningTone} />
            <Stat label="Salary Δ" value={`${salaryDelta <= 0 ? '−' : '+'}${fmtMoney(Math.abs(salaryDelta))}`} sub={`In ${fmtMoney(verdict.costReceived)} · Out ${fmtMoney(verdict.costSent)}`} tone={salaryDelta <= 0 ? 'pos' : 'neg'} />
            {receivedArbTotal > 0 && (
              <Stat label="Arb path (in)" value={fmtMoney(receivedArbTotal)} sub={sentArbTotal > 0 ? `vs ${fmtMoney(sentArbTotal)} out` : '3yr proj.'} tone="neutral" />
            )}
            {verdict.extensionEstReceived > 0 && (
              <Stat
                label="Extension est (in)"
                value={fmtMoney(verdict.extensionEstReceived)}
                sub="realistic lock-up cost · agent leverage"
                tone="neg"
              />
            )}
            {verdict.deadlinePremiumApplied && (
              <div className="flex flex-col gap-0.5">
                <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">Deadline premium</div>
                <div className="font-mono text-[11px] font-bold text-accent-300">Applied</div>
                <div className="text-[10px] text-ink-500">playoff probability uplift included</div>
              </div>
            )}
          </div>
          {/* Win impact */}
          <WinImpact
            warDelta={verdict.warReceived - verdict.warSent}
            currentW={currentW}
            currentL={currentL}
            gamesBack={gamesBack}
            playoffProb={playoffProb}
          />
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-dashed border-ink-700 px-3 py-2.5 text-[11px] text-ink-400">
          <BadgePlus className="h-3.5 w-3.5 text-accent-400/60" />
          Add players to both baskets to activate the verdict.
        </div>
      )}

      {/* Baskets */}
      <div className="mb-3 grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-negative-400">
            ◀ {yourBref} sends
          </div>
          <BasketCard title={`${yourBref} sends`} team={yourTeam} players={sendingPlayers}
            onRemove={id => setSentIds(p => p.filter(x => x !== id))} emptyHint="Pick from your roster below." />
          {/* Prospect adder — sends side */}
          {sentProspects.length > 0 && (
            <div className="mt-1.5 space-y-1">
              {sentProspects.map((q, i) => (
                <div key={i} className="flex items-center justify-between rounded border border-ink-700 bg-ink-900/40 px-2 py-1 text-[11px]">
                  <span className="text-ink-200">{q.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[9px] text-accent-400">{q.fvGrade} FV</span>
                    <button onClick={() => setSentProspects(p => p.filter((_, j) => j !== i))} className="text-ink-600 hover:text-negative-400"><X className="h-3 w-3" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <ProspectAdder onAdd={p => setSentProspects(prev => [...prev, p])} />
        </div>
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-positive-400">
            ▶ {yourBref} receives
          </div>
          <BasketCard title={`${yourBref} receives`} team={partnerTeam} players={receivingPlayers}
            onRemove={id => setReceivedIds(p => p.filter(x => x !== id))} emptyHint="Pick from partner roster below." />
          {/* Prospect adder — receives side */}
          {receivedProspects.length > 0 && (
            <div className="mt-1.5 space-y-1">
              {receivedProspects.map((q, i) => (
                <div key={i} className="flex items-center justify-between rounded border border-ink-700 bg-ink-900/40 px-2 py-1 text-[11px]">
                  <span className="text-ink-200">{q.name}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[9px] text-accent-400">{q.fvGrade} FV</span>
                    <button onClick={() => setReceivedProspects(p => p.filter((_, j) => j !== i))} className="text-ink-600 hover:text-negative-400"><X className="h-3 w-3" /></button>
                  </div>
                </div>
              ))}
            </div>
          )}
          <ProspectAdder onAdd={p => setReceivedProspects(prev => [...prev, p])} />
        </div>
      </div>

      {/* Pickers */}
      <div className="grid gap-3 md:grid-cols-2">
        <PlayerPicker team={yourBref} onPickTeam={() => {}}
          onAdd={p => setSentIds(prev => prev.includes(p.mlb_player_id) ? prev : [...prev, p.mlb_player_id])}
          selectedIds={new Set(sentIds)} title={`${yourBref} roster`} hint={`Click → '${yourBref} sends'`} />
        <PlayerPicker team={partnerBref} onPickTeam={() => {}}
          onAdd={p => setReceivedIds(prev => prev.includes(p.mlb_player_id) ? prev : [...prev, p.mlb_player_id])}
          selectedIds={new Set(receivedIds)} title={`${partnerBref} roster`} hint={`Click → '${yourBref} receives'`} />
      </div>
    </motion.div>
  )
}

// ── buy-low radar ─────────────────────────────────────────────────────────────

function BuyLowRadar({ candidates }: { candidates: BuyLowCandidate[] }) {
  if (candidates.length === 0) return (
    <div className="py-4 text-center font-mono text-[11px] text-ink-500">No buy-low targets found for your holes.</div>
  )
  return (
    <div className="space-y-1.5">
      {candidates.map((c, i) => {
        const topHole = c.holesFilled.sort((a, b) =>
          (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0))[0]
        const postureCfg = POSTURE[c.sourcePosture]
        return (
          <motion.div
            key={c.player.mlb_player_id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className="flex items-center gap-3 rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2"
          >
            <TeamLogo team={c.sourceTeam.bref} size={20} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="truncate text-[12px] font-semibold text-ink-100">{c.player.name}</span>
                <span className={`font-mono text-[8.5px] font-bold ${postureCfg.color}`}>
                  {c.sourceTeam.bref}
                </span>
                <span className="font-mono text-[8.5px] text-ink-500">
                  fills <span className="text-ink-300">{topHole?.position}</span>
                  {topHole?.severity === 'critical' && <span className="ml-0.5 text-negative-500">CRIT</span>}
                </span>
              </div>
              <div className="font-mono text-[10px] text-ink-400">
                {c.player.position_abbr ?? '—'} · {c.player.age ?? '?'}y
                {` · +${c.adjWar.toFixed(1)} WAR · ${fmtMoney(c.yr1Cost)} next · ${c.yearsControlled}yr ctrl`}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className={`font-mono text-[15px] font-black leading-none ${c.valueScore > 3 ? 'text-positive-400' : c.valueScore > 1.8 ? 'text-accent-400' : 'text-ink-300'}`}>
                {c.valueScore.toFixed(1)}×
              </div>
              <div className="flex items-center justify-end gap-0.5 mt-0.5">
                <span className="font-mono text-[8px] text-ink-500">value</span>
                <Cite cite={{ label: 'Value Score', detail: 'Surplus WAR ÷ Year-1 salary cost (normalized). Higher = more production per dollar. 3× = significant buy-low opportunity.' }} />
              </div>
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

// ── deals that clear ──────────────────────────────────────────────────────────

function DealsThatClear({ deals, onSelect }: { deals: DealCandidate[]; onSelect: (bref: string) => void }) {
  if (deals.length === 0) return (
    <div className="py-4 text-center font-mono text-[11px] text-ink-500">No mutual deals found yet.</div>
  )
  return (
    <div className="space-y-2">
      {deals.map((d, i) => {
        const cfg = POSTURE[d.partnerPosture]
        return (
          <motion.button
            key={d.partnerBref}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            whileHover={{ x: 2 }}
            onClick={() => onSelect(d.partnerBref)}
            className="w-full rounded-lg border border-ink-700 bg-ink-900/60 px-3 py-2.5 text-left transition-colors hover:border-ink-600 hover:bg-ink-800/60"
          >
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <TeamLogo team={d.partnerBref} size={20} />
                <span className="font-mono text-[12px] font-bold text-ink-100">{d.partnerBref}</span>
                <span className={`font-mono text-[9px] font-semibold ${cfg.color}`}>{d.partnerPosture.toUpperCase()}</span>
                <span className="font-mono text-[10px] text-ink-400">{d.partnerWL}</span>
              </div>
              <div className="font-mono text-[10px] text-ink-400">
                hdroom <span className={d.partnerHeadroom > 0 ? 'text-positive-400' : 'text-negative-400'}>{fmtMoney(d.partnerHeadroom)}</span>
              </div>
            </div>
            <div className="flex gap-4 text-[10px]">
              <div>
                <span className="font-mono text-[8px] uppercase tracking-wider text-positive-500">They give</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {d.theyFill.map(h => (
                    <span key={h.position} className={`rounded border px-1 py-px font-mono text-[9px] ${h.severity === 'critical' ? 'border-negative-500/40 text-negative-400' : 'border-ink-600 text-ink-300'}`}>
                      {h.position}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <span className="font-mono text-[8px] uppercase tracking-wider text-accent-500">You give</span>
                <div className="mt-0.5 flex flex-wrap gap-1">
                  {d.youFill.map(h => (
                    <span key={h.position} className="rounded border border-ink-600 px-1 py-px font-mono text-[9px] text-ink-300">
                      {h.position}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </motion.button>
        )
      })}
    </div>
  )
}

const SEVERITY_WEIGHT = { critical: 3, warning: 1.5, ok: 0.5 }

// ── arb class helpers ─────────────────────────────────────────────────────────

function advanceArbClass(cls: ArbClass, years: number): ArbClass {
  const seq: ArbClass[] = ['pre-arb', 'arb1', 'arb2', 'arb3', 'fa']
  const i = seq.indexOf(cls)
  return seq[Math.min(i + years, seq.length - 1)]
}

const ARB_CLASS_LABEL: Record<ArbClass, string> = {
  'pre-arb': 'PRE', arb1: 'A1', arb2: 'A2', arb3: 'A3', fa: 'FA',
}
const ARB_CLASS_COLOR: Record<ArbClass, string> = {
  'pre-arb': 'text-positive-400', arb1: 'text-accent-300',
  arb2: 'text-accent-400', arb3: 'text-ink-400', fa: 'text-ink-500',
}

// ── window clock ──────────────────────────────────────────────────────────────

const WINDOW_YEARS = [2026, 2027, 2028, 2029, 2030, 2031]

function warCellStyle(war: number): { bg: string; text: string } {
  if (war > 4.5) return { bg: 'bg-positive-500/25 ring-1 ring-positive-500/40', text: 'text-positive-200' }
  if (war > 3.0) return { bg: 'bg-positive-500/15', text: 'text-positive-300' }
  if (war > 1.5) return { bg: 'bg-positive-500/8',  text: 'text-positive-400' }
  if (war > 0.5) return { bg: 'bg-accent-500/10',   text: 'text-accent-400' }
  if (war > 0.0) return { bg: 'bg-ink-800/80',      text: 'text-ink-500' }
  return { bg: 'bg-ink-900/40', text: 'text-ink-700' }
}

function WindowClock({ players }: { players: CurrentPlayer[] }) {
  const core = useMemo(() => {
    return [...players]
      .filter(p => (p.last_war ?? 0) > 0.3 && p.age != null)
      .sort((a, b) => (b.last_war ?? 0) - (a.last_war ?? 0))
      .slice(0, 10)
  }, [players])

  const rows = useMemo(() => core.map(p => {
    const age0 = p.age!
    const baseWar = Math.max(0, p.last_war ?? 0.5)
    const cls0 = parseArbClass(p.contract_status)
    let war = baseWar
    const years = WINDOW_YEARS.map((yr, t) => {
      war = Math.max(0, war + agingDelta(age0 + t))
      const cls = advanceArbClass(cls0, t + 1)
      return { yr, war, cls }
    })
    return { player: p, years }
  }), [core])

  // team totals per year
  const totals = WINDOW_YEARS.map((_, t) =>
    rows.reduce((sum, r) => sum + r.years[t].war, 0)
  )

  if (rows.length === 0) return null

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 font-mono text-[8.5px] text-ink-600">projected WAR · top 10 contributors · aging curve applied</div>

      {/* Header */}
      <div className="mb-1 grid items-center gap-0.5" style={{ gridTemplateColumns: '8rem repeat(6, 1fr)' }}>
        <div />
        {WINDOW_YEARS.map(yr => (
          <div key={yr} className="text-center font-mono text-[9px] font-semibold text-ink-500">{yr}</div>
        ))}
      </div>

      {/* Player rows */}
      <div className="space-y-0.5">
        {rows.map(({ player: p, years }) => (
          <motion.div
            key={p.mlb_player_id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            className="grid items-center gap-0.5"
            style={{ gridTemplateColumns: '8rem repeat(6, 1fr)' }}
          >
            {/* Player name */}
            <div className="flex min-w-0 items-center gap-1 pr-2">
              <span className="truncate font-mono text-[10px] text-ink-200">{p.name.split(' ').slice(-1)[0]}</span>
              <span className="shrink-0 font-mono text-[8px] text-ink-600">{p.position_abbr ?? '?'}</span>
            </div>
            {/* Year cells */}
            {years.map(({ yr, war, cls }) => {
              const { bg, text } = warCellStyle(war)
              return (
                <div
                  key={yr}
                  title={`${p.name} · ${yr} · ${war.toFixed(1)} WAR · ${ARB_CLASS_LABEL[cls]}`}
                  className={`flex flex-col items-center justify-center rounded py-0.5 ${bg}`}
                >
                  <span className={`font-mono text-[10px] font-bold tabular leading-none ${text}`}>
                    {war > 0 ? war.toFixed(1) : '—'}
                  </span>
                  <span className={`font-mono text-[7px] leading-none ${ARB_CLASS_COLOR[cls]}`}>
                    {ARB_CLASS_LABEL[cls]}
                  </span>
                </div>
              )
            })}
          </motion.div>
        ))}

        {/* Total row */}
        <div className="mt-1 grid items-center gap-0.5 border-t border-ink-700/50 pt-1"
          style={{ gridTemplateColumns: '8rem repeat(6, 1fr)' }}>
          <span className="font-mono text-[9px] font-semibold uppercase tracking-wider text-ink-500">Core total</span>
          {totals.map((tot, t) => {
            const { text } = warCellStyle(tot / 5) // normalize to per-player for coloring
            return (
              <div key={t} className="text-center">
                <span className={`font-mono text-[10px] font-black tabular ${text}`}>{tot.toFixed(0)}</span>
              </div>
            )
          })}
        </div>
      </div>

    </div>
  )
}

// ── payroll timeline ──────────────────────────────────────────────────────────

const PAYROLL_YEARS = ['2026', '2027', '2028']

function PayrollTimeline({ players, cbtThreshold }: { players: CurrentPlayer[]; cbtThreshold: number }) {
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
  }, [players, cbtThreshold])

  const cbtM = cbtThreshold / 1e6
  const maxVal = Math.max(...data.map(d => d.total), cbtM) * 1.15

  const CustomTooltip = ({ active, payload, label }: { active?: boolean; payload?: {color: string; name: string; value: number}[]; label?: string }) => {
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
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
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

// ── win impact strip ─────────────────────────────────────────────────────────

function WinImpact({
  warDelta, currentW, currentL, gamesBack, playoffProb,
}: {
  warDelta: number; currentW: number; currentL: number; gamesBack: number; playoffProb: number
}) {
  const gamesPlayed = currentW + currentL
  const gamesRemaining = Math.max(1, 162 - gamesPlayed)
  // Marginal wins this season from the WAR delta (prorated to games remaining)
  const marginalWins = warDelta * (gamesRemaining / 162)
  const newW = currentW + marginalWins
  const newGB = Math.max(0, gamesBack - marginalWins)
  const newProb = 0.5 * (1 + (1 / (1 + Math.exp(-((newW / (newW + currentL) - 0.5) * 12 - newGB * 0.12 - 0.25)))) * 2 - 1)
  // Use the same logistic formula from computePlayoffProb
  const probBefore = playoffProb
  const probAfter = Math.max(0.02, Math.min(0.97, 1 / (1 + Math.exp(-((newW / (newW + currentL) - 0.5) * 12 - newGB * 0.12 - 0.25)))))
  const delta = probAfter - probBefore
  const sign = marginalWins >= 0 ? '+' : ''
  const deltaSign = delta >= 0 ? '+' : ''
  const color = delta > 0.04 ? 'text-positive-400' : delta > 0 ? 'text-positive-500' : delta < -0.04 ? 'text-negative-400' : 'text-ink-400'

  return (
    <div className="mt-3 flex items-center gap-4 rounded-lg border border-ink-700/50 bg-ink-900/40 px-3 py-2">
      <div className="flex flex-col">
        <span className="font-mono text-[8.5px] uppercase tracking-[0.2em] text-ink-600">Season W Impact</span>
        <span className={`font-mono text-[18px] font-black leading-none tabular ${marginalWins >= 0 ? 'text-positive-400' : 'text-negative-400'}`}>
          {sign}{marginalWins.toFixed(1)}W
        </span>
        <span className="font-mono text-[8.5px] text-ink-600">{gamesRemaining} G remaining</span>
      </div>
      <div className="h-8 w-px bg-ink-700" />
      <div className="flex items-center gap-2">
        <div className="flex flex-col items-center">
          <span className="font-mono text-[8.5px] text-ink-600">Before</span>
          <span className="font-mono text-[16px] font-bold text-ink-400">{Math.round(probBefore * 100)}%</span>
        </div>
        <span className="font-mono text-[10px] text-ink-600">→</span>
        <div className="flex flex-col items-center">
          <span className="font-mono text-[8.5px] text-ink-600">After</span>
          <span className={`font-mono text-[16px] font-bold ${color}`}>{Math.round(probAfter * 100)}%</span>
        </div>
        <span className={`font-mono text-[11px] font-semibold ${color}`}>({deltaSign}{Math.round(delta * 100)}pp)</span>
      </div>
      <div className="ml-auto font-mono text-[8.5px] text-ink-600">P(playoff)</div>
    </div>
  )
}

// ── position market scan ──────────────────────────────────────────────────────

function PositionMarketScan({ candidates, holes }: { candidates: BuyLowCandidate[]; holes: HoleEntry[] }) {
  // Group candidates by their primary hole position
  const byHole = useMemo(() => {
    const map: Record<string, BuyLowCandidate[]> = {}
    for (const c of candidates) {
      const primary = c.holesFilled
        .sort((a, b) => (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0))[0]
      if (!primary) continue
      const pos = primary.position
      if (!map[pos]) map[pos] = []
      map[pos].push(c)
    }
    return map
  }, [candidates])

  // Order by hole severity (critical first)
  const orderedHoles = useMemo(() =>
    [...holes].sort((a, b) => (SEVERITY_WEIGHT[b.severity] ?? 0) - (SEVERITY_WEIGHT[a.severity] ?? 0)),
    [holes]
  )

  if (candidates.length === 0) return (
    <div className="py-4 text-center font-mono text-[11px] text-ink-500">No buy-low targets found for your holes.</div>
  )

  return (
    <div className="space-y-3">
      {orderedHoles.map(hole => {
        const targets = byHole[hole.position]
        if (!targets || targets.length === 0) return null
        const severityColor = hole.severity === 'critical' ? 'text-negative-400 border-negative-500/30' : 'text-accent-300 border-accent-500/30'
        return (
          <div key={hole.position}>
            <div className={`mb-1.5 flex items-center gap-2 border-b pb-1 ${severityColor}`}>
              <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em]">{hole.position}</span>
              {hole.severity === 'critical' && <span className="font-mono text-[8px] font-bold text-negative-500">CRITICAL NEED</span>}
              <span className="ml-auto font-mono text-[8.5px] text-ink-600">{targets.length} targets</span>
            </div>
            <div className="space-y-1">
              {targets.slice(0, 3).map(c => {
                const postureCfg = POSTURE[c.sourcePosture]
                return (
                  <div
                    key={c.player.mlb_player_id}
                    className="flex items-center gap-2.5 rounded border border-ink-700 bg-ink-900/40 px-2.5 py-1.5"
                  >
                    <TeamLogo team={c.sourceTeam.bref} size={18} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate font-mono text-[11px] font-semibold text-ink-100">{c.player.name}</span>
                        <span className={`font-mono text-[8px] font-bold ${postureCfg.color}`}>{c.sourceTeam.bref}</span>
                      </div>
                      <div className="font-mono text-[9.5px] text-ink-400">
                        {c.player.age ?? '?'}y · +{c.adjWar.toFixed(1)} WAR · {fmtMoney(c.yr1Cost)}/yr · {c.yearsControlled}yr ctrl
                      </div>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className={`font-mono text-[14px] font-black leading-none ${c.surplusWar > 4 ? 'text-positive-400' : c.surplusWar > 2 ? 'text-accent-400' : 'text-ink-300'}`}>
                        +{c.surplusWar.toFixed(1)}
                      </div>
                      <div className="flex items-center justify-end gap-0.5 mt-0.5">
                        <span className="font-mono text-[8px] text-ink-600">sWAR</span>
                        <Cite cite={SURPLUS_WAR_CITE} />
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── AI intelligence brief (bring-your-own-Claude) ──────────────────────────────

const KEY_LS = 'warroom-anthropic-key'
const MODEL_LS = 'warroom-anthropic-model'
const DEFAULT_MODEL = 'claude-sonnet-4-5'

function AiBrief({ promptInput }: { promptInput: PromptInput }) {
  const team = promptInput.team.code
  const storageKey = `warroom-brief-${team}`
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [generating, setGenerating] = useState(false)
  const [working, setWorking] = useState(false)        // manual prompt/paste fallback panel
  const [prompt, setPrompt] = useState('')
  const [pasteRaw, setPasteRaw] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [watching, setWatching] = useState(false)     // polling the file-drop inbox
  const [manualPaste, setManualPaste] = useState(false) // reveal the paste fallback
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(DEFAULT_MODEL)
  const abortRef = useRef<AbortController | null>(null)

  // Load key/model once
  useEffect(() => {
    try {
      setApiKey(localStorage.getItem(KEY_LS) ?? '')
      setModel(localStorage.getItem(MODEL_LS) || DEFAULT_MODEL)
    } catch { /* ignore */ }
  }, [])
  useEffect(() => { try { localStorage.setItem(KEY_LS, apiKey) } catch { /* ignore */ } }, [apiKey])
  useEffect(() => { try { localStorage.setItem(MODEL_LS, model) } catch { /* ignore */ } }, [model])

  // Load the brief when the team changes: localStorage first (instant), then the
  // DuckDB-exported inbox file (canonical source of truth) if one is present.
  useEffect(() => {
    setReport(null); setWorking(false); setPrompt(''); setPasteRaw(''); setError(null)
    setFullscreen(false); setWatching(false); setManualPaste(false)
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) setReport(JSON.parse(saved) as AnalysisReport)
    } catch { /* ignore corrupt cache */ }
    let alive = true
    fetch(`/brief-inbox/${team}.json?t=${Date.now()}`, { cache: 'no-store' })
      .then(r => (r.ok ? r.text() : null))
      .then(text => {
        if (!alive || !text || !text.trim()) return
        try {
          const r = parseAnalysisReport(text); r.team = team
          setReport(r)
          try { localStorage.setItem(storageKey, JSON.stringify(r)) } catch { /* quota */ }
        } catch { /* no valid brief on disk yet */ }
      })
      .catch(() => { /* offline / missing */ })
    return () => { alive = false }
  }, [storageKey, team])

  const persist = (r: AnalysisReport) => { try { localStorage.setItem(storageKey, JSON.stringify(r)) } catch { /* quota */ } }
  const accept = (raw: string) => {
    const r = parseAnalysisReport(raw); r.team = team
    setReport(r); persist(r); setError(null); setWorking(false); setWatching(false)
  }

  // File-drop bridge (SHC pattern): poll the inbox a Claude Code run writes to.
  // Vite serves frontend/public at root, so a run that writes
  // frontend/public/brief-inbox/<TEAM>.json lands at /brief-inbox/<TEAM>.json.
  useEffect(() => {
    if (!watching) return
    let alive = true
    const tick = async () => {
      try {
        const res = await fetch(`/brief-inbox/${team}.json?t=${Date.now()}`, { cache: 'no-store' })
        if (!res.ok || !alive) return
        const text = await res.text()
        if (!text.trim()) return
        try { accept(text) } catch { /* not a valid brief yet — keep polling */ }
      } catch { /* network/404 — keep polling */ }
    }
    void tick()
    const id = window.setInterval(tick, 3000)
    return () => { alive = false; window.clearInterval(id) }
  }, [watching, team])

  const generateLive = async () => {
    setError(null)
    const p = buildAnalysisPrompt(promptInput)
    setPrompt(p)
    if (!apiKey.trim()) {
      setSettingsOpen(true); setWorking(true)
      navigator.clipboard?.writeText(p).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {})
      setError('No API key set — add one above to generate in-app, or copy the prompt below and paste Claude\'s reply.')
      return
    }
    setGenerating(true)
    const ctrl = new AbortController(); abortRef.current = ctrl
    try {
      const raw = await generateBriefRaw(p, { apiKey: apiKey.trim(), model: model.trim() || DEFAULT_MODEL, signal: ctrl.signal })
      accept(raw)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') { /* cancelled */ }
      else {
        setError(`${e instanceof Error ? e.message : 'Generation failed.'} — or copy the prompt below and paste Claude's reply.`)
        setWorking(true)
        navigator.clipboard?.writeText(p).catch(() => {})
      }
    } finally { setGenerating(false); abortRef.current = null }
  }

  const cancel = () => { abortRef.current?.abort(); setGenerating(false) }
  const generatePrompt = () => {
    const p = buildAnalysisPrompt(promptInput)
    setPrompt(p)
    setWorking(true)
    setWatching(true)        // start watching the inbox for a Claude Code drop
    setError(null)
    navigator.clipboard?.writeText(p)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
      .catch(() => { /* clipboard blocked; prompt still visible */ })
  }
  const copyPrompt = () => {
    const p = prompt || buildAnalysisPrompt(promptInput)
    navigator.clipboard?.writeText(p).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {})
  }
  const renderPasted = () => {
    try { accept(pasteRaw) } catch (e) { setError(e instanceof Error ? e.message : 'Could not parse the response.') }
  }
  const clear = () => {
    setReport(null); setPasteRaw(''); setError(null); setFullscreen(false); setWatching(false)
    try { localStorage.removeItem(storageKey) } catch { /* ignore */ }
  }

  const header = (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <Brain className="h-4 w-4 text-accent-400" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-200">AI Intelligence Brief</span>
        <span className="font-mono text-[8.5px] text-ink-500">full-data strategic analysis</span>
      </div>
      <div className="flex items-center gap-1.5">
        <button onClick={() => setSettingsOpen(s => !s)} title="API settings"
          className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-400 transition-colors hover:border-accent-500/40 hover:text-accent-300">
          <Settings className="h-3 w-3" />
        </button>
        {report && (
          <button onClick={() => setFullscreen(true)}
            className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-400 transition-colors hover:border-accent-500/40 hover:text-accent-300">
            <Maximize2 className="h-3 w-3" />EXPAND
          </button>
        )}
        {!generating ? (
          <>
            <button onClick={generatePrompt}
              className="flex items-center gap-1 rounded border border-accent-500/40 bg-accent-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-accent-300 transition-colors hover:bg-accent-500/20">
              <FileText className="h-3 w-3" />{report ? 'REGENERATE PROMPT' : 'GENERATE PROMPT'}
            </button>
            <button onClick={generateLive} title="Generate in-app via the Anthropic API (needs a key in settings)"
              className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-400 transition-colors hover:border-accent-500/40 hover:text-accent-300">
              <Wand2 className="h-3 w-3" />RUN IN-APP
            </button>
          </>
        ) : (
          <button onClick={cancel}
            className="flex items-center gap-1 rounded border border-negative-500/40 bg-negative-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-negative-400">
            <X className="h-3 w-3" />CANCEL
          </button>
        )}
        {report && (
          <button onClick={clear}
            className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-500 transition-colors hover:border-negative-500/40 hover:text-negative-400">
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  )

  return (
    <div className="rounded-lg border border-accent-500/25 bg-gradient-to-b from-accent-500/[0.05] to-transparent p-4">
      {header}

      {/* Settings: API key + model */}
      {settingsOpen && (
        <div className="mb-3 rounded-lg border border-ink-700 bg-ink-900/60 p-3">
          <div className="mb-2 flex items-center gap-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
            <KeyRound className="h-3 w-3" />Anthropic API
          </div>
          <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
            <input
              type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
              placeholder="sk-ant-… (stored only in this browser)"
              className="rounded border border-ink-700 bg-ink-950/60 px-2 py-1 font-mono text-[10px] text-ink-200 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
            />
            <input
              type="text" value={model} onChange={e => setModel(e.target.value)}
              placeholder="model id"
              className="rounded border border-ink-700 bg-ink-950/60 px-2 py-1 font-mono text-[10px] text-ink-200 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
            />
          </div>
          <p className="mt-1.5 font-mono text-[8px] leading-relaxed text-ink-600">
            Key is stored in this browser's localStorage and sent directly to Anthropic (dangerous-direct-browser-access).
            Fine for a local personal tool; for a public deploy, proxy through a backend. Update the model id if your account uses a different one.
          </p>
        </div>
      )}

      {/* Generating banner */}
      {generating && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-accent-500/30 bg-accent-500/[0.06] px-3 py-2.5">
          <Loader2 className="h-4 w-4 animate-spin text-accent-400" />
          <span className="font-mono text-[11px] text-accent-300">Consulting Claude — drafting the brief…</span>
        </div>
      )}

      {/* Watching inbox banner (file-drop bridge) */}
      {watching && !report && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-positive-500/25 bg-positive-500/[0.05] px-3 py-2.5">
          <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.4 }}
            className="inline-block h-2 w-2 shrink-0 rounded-full bg-positive-400" />
          <span className="flex-1 font-mono text-[10px] leading-relaxed text-positive-300">
            Watching <span className="text-positive-200">brief-inbox/{team}.json</span> — run the prompt in Claude Code and it lands here automatically.
          </span>
          <button onClick={() => setWatching(false)} className="font-mono text-[9px] text-ink-500 hover:text-ink-300">stop</button>
        </div>
      )}

      {/* Manual fallback: prompt + paste */}
      {working && !generating && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-4 space-y-3">
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
                ① copy prompt → run in Claude Code
              </span>
              <button onClick={copyPrompt} className="flex items-center gap-1 rounded border border-ink-700 px-1.5 py-0.5 font-mono text-[8.5px] text-ink-400 hover:text-accent-300">
                {copied ? <><Check className="h-2.5 w-2.5 text-positive-400" />COPIED</> : <><ClipboardCopy className="h-2.5 w-2.5" />COPY</>}
              </button>
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-ink-950/60 p-2 font-mono text-[9px] leading-relaxed text-ink-400">{prompt}</pre>
          </div>
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
            <div className="font-mono text-[9px] leading-relaxed text-ink-400">
              <span className="font-semibold uppercase tracking-[0.2em] text-positive-300">② it uploads itself</span><br />
              Run the prompt in Claude Code — or just <span className="text-ink-200">/trade-brief {team}</span> — and it persists to
              DuckDB and writes the inbox. This panel renders it automatically. No pasting.
            </div>
            <button onClick={() => setManualPaste(v => !v)} className="mt-2 font-mono text-[9px] text-ink-600 hover:text-ink-300">
              {manualPaste ? '▾ hide manual paste' : '▸ paste the response manually instead'}
            </button>
            {manualPaste && (
              <div className="mt-2">
                <textarea
                  value={pasteRaw} onChange={e => setPasteRaw(e.target.value)}
                  placeholder="Paste the full response — fences and prose handled automatically…" rows={4}
                  className="w-full resize-y rounded border border-ink-700 bg-ink-950/60 p-2 font-mono text-[10px] text-ink-200 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
                />
                <button onClick={renderPasted} disabled={!pasteRaw.trim()}
                  className="mt-2 flex items-center gap-1 rounded border border-positive-500/40 bg-positive-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-positive-400 transition-colors hover:bg-positive-500/20 disabled:cursor-not-allowed disabled:opacity-40">
                  <RefreshCw className="h-3 w-3" />RENDER BRIEF
                </button>
              </div>
            )}
            <div className="mt-2">
              <button onClick={() => { setWorking(false); setError(null) }} className="font-mono text-[9px] text-ink-600 hover:text-ink-300">close</button>
            </div>
          </div>
        </motion.div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-3 flex items-start gap-1.5 rounded border border-negative-500/30 bg-negative-500/5 px-2 py-1.5 font-mono text-[9px] leading-relaxed text-negative-400">
          <X className="mt-0.5 h-3 w-3 shrink-0" />{error}
        </div>
      )}

      {/* Empty CTA */}
      {!report && !generating && !working && (
        <div className="rounded-lg border border-dashed border-accent-500/20 bg-accent-500/[0.03] px-6 py-8">
          <div className="flex flex-col items-center text-center">
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-xl border border-accent-500/25 bg-accent-500/[0.08]">
              <Brain className="h-7 w-7 text-accent-400" />
            </div>
            <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-ink-300">
              Strategic Brief — Not Yet Generated
            </div>
            <p className="mb-5 max-w-lg text-[11px] leading-relaxed text-ink-500">
              One click pre-loads standings, holes, payroll, the contention window, buy-low targets, and
              clearing deals into a structured GM prompt. Run it in Claude Code with{' '}
              <span className="font-mono text-accent-300">/trade-brief {promptInput.team.code}</span>{' '}
              and it renders here automatically — no paste required.
            </p>
            <div className="flex items-center gap-3">
              <div className="flex flex-col items-start gap-1 rounded-lg border border-ink-700 bg-ink-900/80 px-4 py-3 text-left">
                <span className="font-mono text-[8px] uppercase tracking-[0.2em] text-ink-500">Claude Code</span>
                <span className="font-mono text-[12px] font-bold text-accent-300">/trade-brief {promptInput.team.code}</span>
              </div>
              <span className="font-mono text-[10px] text-ink-600">or</span>
              <div className="flex flex-col items-start gap-1 rounded-lg border border-ink-700 bg-ink-900/80 px-4 py-3 text-left">
                <span className="font-mono text-[8px] uppercase tracking-[0.2em] text-ink-500">In-app (API key required)</span>
                <span className="font-mono text-[12px] font-bold text-ink-300">Settings → Run In-App</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Rendered brief (inline) */}
      {report && !fullscreen && <IntelligenceReport report={report} />}

      {/* Fullscreen brief screen */}
      {report && fullscreen && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-ink-950/98 backdrop-blur-sm">
          <div className="mx-auto max-w-[1200px] px-6 py-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-accent-400" />
                <span className="display text-[18px] font-black text-ink-100">{team} · Intelligence Brief</span>
              </div>
              <button onClick={() => setFullscreen(false)}
                className="flex items-center gap-1 rounded border border-ink-700 px-2.5 py-1 font-mono text-[10px] text-ink-300 transition-colors hover:border-accent-500/40 hover:text-accent-300">
                <X className="h-3.5 w-3.5" />CLOSE
              </button>
            </div>
            <IntelligenceReport report={report} />
          </div>
        </div>
      )}
    </div>
  )
}

// ── main ───────────────────────────────────────────────────────────────────────

export default function WarRoom() {
  const active = useIdentityStore(s => s.activeTeam)
  const roster = useRoster()
  const [yourPayload, setYourPayload] = useState<TeamPayload | null>(null)
  const [partnerBref, setPartnerBref] = useState<string | null>(null)
  const [partnerPayload, setPartnerPayload] = useState<TeamPayload | null>(null)
  const [allPayloads, setAllPayloads] = useState<Record<string, TeamPayload> | null>(null)
  const [phase2Loading, setPhase2Loading] = useState(false)
  const [phase2Open, setPhase2Open] = useState(false)

  useEffect(() => {
    let alive = true
    setYourPayload(null)
    loadTeamPayload(active).then(p => { if (alive) setYourPayload(p) })
    return () => { alive = false }
  }, [active])

  useEffect(() => {
    if (!partnerBref) { setPartnerPayload(null); return }
    let alive = true
    setPartnerPayload(null)
    loadTeamPayload(partnerBref).then(p => { if (alive) setPartnerPayload(p) })
    return () => { alive = false }
  }, [partnerBref])

  // Lazy-load all 30 payloads when Phase 2 panel is opened
  useEffect(() => {
    if (!phase2Open || allPayloads) return
    setPhase2Loading(true)
    loadAllTeamPayloads().then(all => {
      setAllPayloads(all)
      setPhase2Loading(false)
    })
  }, [phase2Open, allPayloads])

  const indexTeam = warRoomIndex.teams.find(t => t.code === active)
  if (!indexTeam) return (
    <div className="mx-auto max-w-[1480px] px-6 py-10 font-mono text-[12px] text-ink-500">
      No data for {active}.
    </div>
  )

  const headroom = indexTeam.payrollHeadroom
  const ctx = yourPayload?.context
  const devMul = DEV_SIGNATURE[active] ?? 1.0

  const deals = useMemo(() =>
    yourPayload && allPayloads ? computeDeals(active, yourPayload, allPayloads) : [],
    [active, yourPayload, allPayloads],
  )

  const buyLow = useMemo(() =>
    yourPayload && allPayloads
      ? computeBuyLow(active, yourPayload, roster.teams, allPayloads, devMul)
      : [],
    [active, yourPayload, allPayloads, roster.teams, devMul],
  )

  const teamPlayers = roster.teams.find(t => t.bref === active)?.players ?? []

  return (
    <div className="mx-auto max-w-[1480px] px-4 py-6">
      {/* Page header */}
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <TeamLogo team={active} size={44} />
          <div>
            <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.25em] text-accent-400">
              WAR ROOM · SEASON INTELLIGENCE
            </div>
            <h1 className="display text-[30px] font-black leading-tight tracking-tight text-ink-100">
              {indexTeam.name}
            </h1>
            <div className="font-mono text-[10px] text-ink-400">{indexTeam.division}</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="font-mono text-right text-[10px] text-ink-400">
            <div>{warRoomIndex.season} SEASON · {warRoomIndex.asOfGames} GP</div>
            <div className="text-ink-500">blend w₂₀₂₆={warRoomIndex.blendWeight.toFixed(2)}</div>
          </div>
          <div className="flex items-center gap-1.5 rounded-md border border-ink-700 bg-ink-900 px-2.5 py-1.5">
            <PulseDot color="bg-positive-500" />
            <span className="font-mono text-[9px] font-semibold text-positive-400">LIVE</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[240px_1fr]">
        {/* Left: league board */}
        <aside className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
          <div className="mb-2 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
            30-team board · click to analyze
          </div>
          <LeagueTicker yourBref={active} partnerBref={partnerBref} onSelect={setPartnerBref} />
        </aside>

        {/* Right: main intel */}
        <div className="min-w-0 space-y-4">
          <AnimatePresence mode="wait">
            {yourPayload ? (
              <motion.div key={active} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">

                {/* 1 — Posture banner (record + GB embedded) */}
                <PostureBanner
                  posture={indexTeam.windowPosture}
                  rationale={ctx?.postureRationale ?? ''}
                  playoffProb={computePlayoffProb(indexTeam.w, indexTeam.l, indexTeam.gamesBack)}
                  w={indexTeam.w}
                  l={indexTeam.l}
                  gamesBack={indexTeam.gamesBack}
                />

                {/* 2 — Payroll intelligence */}
                <div className="space-y-3">
                  <SectionHeader label="Payroll Intelligence" cite={{ label: 'Heuristic layer', detail: 'Pre-model. In-season stats shrunk toward 2025 prior. Contextual posteriors: Phase 2.' }} />
                  <PayrollGauge
                    committed={indexTeam.payrollCommitted}
                    threshold={warRoomIndex.cbtThreshold}
                    headroom={headroom}
                  />
                  {ctx && ctx.expiringContracts.length > 0 ? (
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
                        <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
                          Top commitments
                        </div>
                        <div className="space-y-1.5">
                          {ctx.expiringContracts.map((c, i) => (
                            <motion.div
                              key={c.player}
                              initial={{ opacity: 0, x: -6 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: i * 0.04 }}
                              className="flex items-center justify-between gap-2"
                            >
                              <span className="truncate text-[11px] text-ink-200">{c.player}</span>
                              {c.position && (
                                <span className="shrink-0 rounded bg-ink-800 px-1 py-0.5 font-mono text-[9px] text-ink-400">
                                  {c.position}
                                </span>
                              )}
                              <span className="font-mono shrink-0 text-[11px] tabular text-ink-300">
                                {money(c.capHit)}
                              </span>
                            </motion.div>
                          ))}
                        </div>
                      </div>
                      <PayrollTimeline players={teamPlayers} cbtThreshold={warRoomIndex.cbtThreshold} />
                    </div>
                  ) : (
                    <PayrollTimeline players={teamPlayers} cbtThreshold={warRoomIndex.cbtThreshold} />
                  )}
                </div>

                {/* 3 — Roster shape: positional radar + holes/surpluses unified */}
                <div className="space-y-3">
                  <SectionHeader label="Roster Shape" />
                  <div className="grid gap-4 md:grid-cols-2">
                    <PositionRadar
                      holes={yourPayload.holes}
                      surpluses={yourPayload.surpluses}
                      posture={indexTeam.windowPosture}
                    />
                    <HolesBoard
                      holes={yourPayload.holes}
                      surpluses={yourPayload.surpluses}
                    />
                  </div>
                </div>

                {/* 4 — Contention window */}
                <div className="space-y-3">
                  <SectionHeader label="Contention Window" cite={{ label: 'Contention Window', detail: 'Projected WAR for top-10 contributors by year, applying the aging curve (delta-method). Dev-system multiplier not applied — raw age trajectory only. Arb class shows cost escalation path.' }} />
                  <WindowClock players={teamPlayers} />
                </div>

                {/* 5 — Intelligence feed (always visible, not gated by partner selection) */}
                <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Sparkles className="h-3.5 w-3.5 text-accent-400" />
                      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-300">
                        Intelligence Feed
                      </span>
                      <Cite cite={{ label: 'Intelligence Feed', detail: 'Buy-low targets: players on sellers whose surplus WAR fills your positional holes. Deals that clear: teams where your surpluses fill their holes and vice versa — mutual fit.' }} />
                    </div>
                    {!phase2Open ? (
                      <button
                        onClick={() => setPhase2Open(true)}
                        className="rounded border border-accent-500/40 bg-accent-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-accent-300 transition-colors hover:bg-accent-500/20"
                      >
                        LOAD ANALYSIS
                      </button>
                    ) : phase2Loading ? (
                      <span className="font-mono text-[9px] text-ink-500">Loading 30 teams…</span>
                    ) : null}
                  </div>
                  {!phase2Open ? (
                    <div className="flex items-center gap-3 py-3">
                      <Sparkles className="h-5 w-5 text-accent-400/40 shrink-0" />
                      <p className="text-[11px] leading-relaxed text-ink-400">
                        Cross-reference all 30 rosters for buy-low targets and mutual trade fits.
                        <span className="ml-1 text-accent-300">Load analysis to activate.</span>
                      </p>
                    </div>
                  ) : phase2Loading ? (
                    <div className="flex items-center gap-2 py-4 font-mono text-[11px] text-ink-500">
                      <motion.span animate={{ opacity: [0.4, 1, 0.4] }} transition={{ repeat: Infinity, duration: 1.2 }}>
                        Scanning league…
                      </motion.span>
                    </div>
                  ) : (
                    <div className="grid gap-5 md:grid-cols-2">
                      <div>
                        <div className="mb-2 flex items-center gap-1.5">
                          <Sparkles className="h-3 w-3 text-positive-400" />
                          <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-positive-400">
                            Position Market Scan
                          </span>
                          <span className="font-mono text-[8.5px] text-ink-500">by hole · control-window surplus WAR</span>
                        </div>
                        <PositionMarketScan candidates={buyLow} holes={yourPayload.holes} />
                      </div>
                      <div>
                        <div className="mb-2 flex items-center gap-1.5">
                          <Target className="h-3 w-3 text-accent-400" />
                          <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-accent-400">
                            Deals that clear
                          </span>
                          <span className="font-mono text-[8.5px] text-ink-500">mutual hole/surplus match</span>
                        </div>
                        <DealsThatClear deals={deals} onSelect={setPartnerBref} />
                      </div>
                    </div>
                  )}
                </div>

                {/* 6 — Partner panel + trade workshop (co-located) */}
                <AnimatePresence>
                  {partnerBref && (
                    <motion.div
                      key={`partner-${partnerBref}`}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 10 }}
                      className="space-y-4"
                    >
                      <PartnerPanel
                        bref={partnerBref}
                        payload={partnerPayload}
                        onClose={() => setPartnerBref(null)}
                      />
                      <TradeWorkshop
                        yourBref={active}
                        partnerBref={partnerBref}
                        verdictCtx={{
                          yourPosture: indexTeam.windowPosture,
                          playoffProb: computePlayoffProb(indexTeam.w, indexTeam.l, indexTeam.gamesBack),
                          currentW: indexTeam.w,
                          currentL: indexTeam.l,
                          gamesBack: indexTeam.gamesBack,
                        }}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* 7 — AI intelligence brief (always mounted) */}
                <AiBrief
                  promptInput={{
                    team: indexTeam,
                    payload: yourPayload,
                    rosterPlayers: teamPlayers,
                    buyLow,
                    deals,
                    cbtThreshold: warRoomIndex.cbtThreshold,
                    season: warRoomIndex.season,
                    playoffProb: computePlayoffProb(indexTeam.w, indexTeam.l, indexTeam.gamesBack),
                    allTeams: roster.teams,
                    allPayloads: allPayloads ?? {},
                  }}
                />

              </motion.div>
            ) : (
              <div className="flex items-center justify-center py-20 font-mono text-[11px] text-ink-600">
                Loading {active} intel…
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
