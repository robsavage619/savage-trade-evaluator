import { useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence, useMotionValue, useSpring } from 'framer-motion'
import CountUp from 'react-countup'
import {
  TrendingUp, TrendingDown, Minus, Info, Sparkles, Target,
  ArrowLeftRight, Trash2, X, BadgePlus, ChevronRight, Radio,
} from 'lucide-react'
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer,
} from 'recharts'
import { useIdentityStore } from '../lib/identityStore'
import { warRoomIndex, loadTeamPayload } from '../lib/warroomData'
import type { Citation, HoleEntry, TeamPayload, WindowPosture } from '../data/warroom/types'
import { TeamLogo } from '../components/TeamLogo'
import { PlayerPicker, BasketCard } from '../components/PlayerPicker'
import { Stat } from '../components/Section'
import { forecastArb, isControlled } from '../lib/arbForecast'
import { computeVerdict } from '../lib/hypothetical'
import type { CurrentPlayer } from '../data/players'
import { useTeamsByBref } from '../lib/rosterStore'
import { fmtMoney } from '../lib/format'

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
      <span className="pointer-events-none absolute bottom-[calc(100%+6px)] left-1/2 z-50 hidden w-64 -translate-x-1/2 rounded border border-ink-700 bg-ink-900 p-2 text-left text-[10px] leading-relaxed text-ink-300 shadow-xl group-hover:block">
        <span className="font-semibold text-ink-100">{cite.label}</span><br />{cite.detail}
      </span>
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

// ── posture banner ───────────────────────────────────────────────────────────

function PostureBanner({ posture, rationale }: { posture: WindowPosture; rationale: string }) {
  const cfg = POSTURE[posture]
  const Icon = cfg.Icon
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
      <div className="flex items-center gap-4">
        <div className={`grid h-14 w-14 shrink-0 place-items-center rounded-lg border-2 ${cfg.border} ${cfg.bg}`}>
          <Icon className={`h-7 w-7 ${cfg.color}`} strokeWidth={2.5} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center gap-2">
            <PulseDot color={cfg.dot} />
            <span className={`font-mono text-[10px] font-semibold uppercase tracking-[0.25em] ${cfg.color}`}>
              WINDOW ASSESSMENT
            </span>
          </div>
          <div className={`display text-[28px] font-black leading-none tracking-tight ${cfg.color}`}>
            {cfg.label}
          </div>
          <p className="mt-1.5 text-[11px] leading-relaxed text-ink-300">{rationale}</p>
        </div>
      </div>
    </motion.div>
  )
}

// ── animated stat block ──────────────────────────────────────────────────────

function LiveStat({
  label, value, sub, tone = 'neutral', prefix = '', suffix = '', decimals = 0,
}: {
  label: string; value: number; sub?: string; tone?: 'pos' | 'neg' | 'neutral'
  prefix?: string; suffix?: string; decimals?: number
}) {
  const color = tone === 'pos' ? 'text-positive-500' : tone === 'neg' ? 'text-negative-500' : 'text-ink-100'
  return (
    <div className="flex flex-col gap-0.5">
      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">{label}</div>
      <div className={`font-mono text-[22px] font-black tabular leading-none ${color}`}>
        {prefix}
        <CountUp end={value} duration={1.2} decimals={decimals} separator="," preserveValue />
        {suffix}
      </div>
      {sub && <div className="text-[10px] text-ink-500">{sub}</div>}
    </div>
  )
}

// ── payroll gauge ────────────────────────────────────────────────────────────

function PayrollGauge({ committed, threshold, headroom }: { committed: number; threshold: number; headroom: number }) {
  const pct = Math.min(100, (committed / threshold) * 100)
  const over = committed > threshold
  const barColor = over ? '#ff5d73' : pct > 85 ? '#ff8a3d' : '#3ddc97'

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">Payroll vs CBT</span>
        <span className={`font-mono text-[10px] font-semibold ${over ? 'text-negative-500' : 'text-positive-500'}`}>
          {over ? 'OVER CBT' : 'UNDER CBT'}
        </span>
      </div>
      {/* Bar */}
      <div className="relative mb-2 h-3 overflow-hidden rounded-full bg-ink-800">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 1.0, ease: 'easeOut' }}
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ background: barColor, boxShadow: `0 0 10px ${barColor}60` }}
        />
        {/* CBT line marker */}
        <div className="absolute inset-y-0 right-0 w-px bg-ink-500" style={{ right: '0%' }} />
      </div>
      <div className="flex items-baseline justify-between">
        <div className="font-mono text-[11px] text-ink-300">
          <CountUp end={committed / 1_000_000} duration={1.2} decimals={1} prefix="$" suffix="M" preserveValue />
          <span className="text-ink-600"> / </span>
          <span className="text-ink-500">{money(threshold)}</span>
        </div>
        <div className={`font-mono text-[13px] font-bold ${over ? 'text-negative-500' : 'text-positive-500'}`}>
          {over ? '−' : '+'}
          <CountUp end={Math.abs(headroom) / 1_000_000} duration={1.2} decimals={1} suffix="M" preserveValue />
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
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">Position Shape</span>
        <Cite cite={{ label: 'Replacement baseline', detail: '0 = critical gap · 50 = replacement level · 100 = tradeable surplus' }} />
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

function HolesBoard({ holes, surpluses, cite }: { holes: HoleEntry[]; surpluses: HoleEntry[]; cite: Citation }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">Position Assessment</span>
        <Cite cite={cite} />
      </div>
      {holes.length > 0 && (
        <div className="mb-3">
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-negative-500">
            ▼ Needs
          </div>
          <div className="space-y-1">
            {holes.map((h, i) => (
              <motion.div
                key={h.position}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="flex items-center gap-2.5"
                style={{ borderLeft: `2px solid ${SEVERITY_COLOR[h.severity]}` }}
              >
                <span className="font-mono w-8 shrink-0 pl-2 text-[11px] font-bold text-ink-100">{h.position}</span>
                <div className="relative flex-1 h-1.5 overflow-hidden rounded-full bg-ink-800">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (h.holeScore / h.replacementBaseline) * 100)}%` }}
                    transition={{ duration: 0.7, delay: i * 0.05, ease: 'easeOut' }}
                    className="absolute inset-y-0 left-0 rounded-full"
                    style={{ background: SEVERITY_COLOR[h.severity] }}
                  />
                </div>
                <span className="font-mono shrink-0 text-[11px] font-semibold text-negative-400">
                  −{h.holeScore.toFixed(1)}
                </span>
                {h.severity === 'critical' && (
                  <span className="font-mono shrink-0 text-[8px] font-bold uppercase tracking-wider text-negative-500">CRIT</span>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      )}
      {surpluses.length > 0 && (
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-positive-500">
            ▲ Tradeable surplus
          </div>
          <div className="space-y-1">
            {surpluses.map((h, i) => (
              <motion.div
                key={h.position}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 + 0.15 }}
                className="flex items-center gap-2.5 border-l-2 border-positive-500/40"
              >
                <span className="font-mono w-8 shrink-0 pl-2 text-[11px] font-bold text-ink-100">{h.position}</span>
                <div className="relative flex-1 h-1.5 overflow-hidden rounded-full bg-ink-800">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, ((h.surplus ?? 0) / h.replacementBaseline) * 100)}%` }}
                    transition={{ duration: 0.7, delay: i * 0.05 + 0.15, ease: 'easeOut' }}
                    className="absolute inset-y-0 left-0 rounded-full bg-positive-500/60"
                  />
                </div>
                <span className="font-mono shrink-0 text-[11px] font-semibold text-positive-400">
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
          <div className="mb-1 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-ink-600">{div}</div>
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
                  <span className="font-mono text-[10px] tabular text-ink-500">{t.w}–{t.l}</span>
                  <span className={`font-mono ml-auto text-[9px] font-semibold ${cfg.color} ${isYou || isPartner ? 'opacity-100' : 'opacity-50'}`}>
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
            <div className="font-mono text-[10px] text-ink-400">
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
        <span className="text-ink-500">Payroll <span className="text-ink-200">{money(idx.payrollCommitted)}</span></span>
        <span className={idx.payrollHeadroom < 0 ? 'text-negative-400' : 'text-positive-400'}>
          Hdroom {money(idx.payrollHeadroom)}
        </span>
      </div>

      {payload ? (
        <>
          {payload.context.postureRationale && (
            <p className="mb-3 text-[11px] leading-relaxed text-ink-400">{payload.context.postureRationale}</p>
          )}
          <HolesBoard
            holes={payload.holes}
            surpluses={payload.surpluses}
            cite={payload.holes[0]?.citation ?? payload.context.citation}
          />
          {payload.context.expiringContracts.length > 0 && (
            <div className="mt-3 rounded-lg border border-ink-700 bg-ink-900/60 p-3">
              <div className="mb-2 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-ink-500">Their commitments</div>
              <div className="space-y-1">
                {payload.context.expiringContracts.map(c => (
                  <div key={c.player} className="flex items-center justify-between text-[11px]">
                    <span className="truncate text-ink-300">{c.player}</span>
                    <span className="font-mono shrink-0 text-ink-400">{money(c.capHit)}</span>
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

// ── trade workshop ─────────────────────────────────────────────────────────────

function TradeWorkshop({ yourBref, partnerBref }: { yourBref: string; partnerBref: string }) {
  const teamsByBref = useTeamsByBref()
  const yourTeam = teamsByBref[yourBref]
  const partnerTeam = teamsByBref[partnerBref]
  const [sentIds, setSentIds] = useState<number[]>([])
  const [receivedIds, setReceivedIds] = useState<number[]>([])

  useEffect(() => { setSentIds([]); setReceivedIds([]) }, [partnerBref])

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
      ? computeVerdict({ sending: { team: yourTeam, players: sendingPlayers }, receiving: { team: partnerTeam, players: receivingPlayers } })
      : null,
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers],
  )

  const receivedArbTotal = useMemo(() =>
    receivingPlayers.reduce((acc, p) => {
      const a = forecastArb(p.contract_status, p.last_war, p.cap_hit)
      return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
    }, 0), [receivingPlayers],
  )
  const sentArbTotal = useMemo(() =>
    sendingPlayers.reduce((acc, p) => {
      const a = forecastArb(p.contract_status, p.last_war, p.cap_hit)
      return acc + (isControlled(a.currentClass) ? a.totalCost3yr : 0)
    }, 0), [sendingPlayers],
  )

  if (!yourTeam || !partnerTeam) return null

  const salaryDelta = (verdict?.costReceived ?? 0) - (verdict?.costSent ?? 0)
  const rec = verdict?.recommendation
  const recColor = rec === 'strong-buy' || rec === 'lean-buy'
    ? 'text-positive-500 border-positive-500/30 bg-positive-500/5'
    : rec === 'strong-pass' || rec === 'lean-pass'
    ? 'text-negative-500 border-negative-500/30 bg-negative-500/5'
    : 'text-ink-300 border-ink-700 bg-ink-800/40'

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
          <span className="font-mono text-[10px] text-ink-600">
            {yourBref} <ArrowLeftRight className="inline h-2.5 w-2.5" /> {partnerBref}
          </span>
        </div>
        <button
          onClick={() => { setSentIds([]); setReceivedIds([]) }}
          className="flex items-center gap-1 font-mono text-[9px] text-ink-600 transition-colors hover:text-negative-400"
        >
          <Trash2 className="h-3 w-3" /> CLEAR
        </button>
      </div>

      {/* Verdict */}
      {verdict ? (
        <div className={`mb-4 rounded-lg border p-3 ${recColor}`}>
          <div className="mb-2 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] opacity-60">
            GM Decision Signal
          </div>
          <div className="flex flex-wrap gap-5">
            <Stat label="3-yr surplus" value={`${verdict.surplusMean >= 0 ? '+' : ''}${verdict.surplusMean.toFixed(1)} WAR`} sub={`P(+) ${Math.round(verdict.pPositive * 100)}%`} tone={verdict.reasoningTone} />
            <Stat label="WAR Δ" value={`${(verdict.warReceived - verdict.warSent) >= 0 ? '+' : ''}${(verdict.warReceived - verdict.warSent).toFixed(1)}`} sub="dev-adjusted" tone={verdict.reasoningTone} />
            <Stat label="Salary Δ" value={`${salaryDelta <= 0 ? '−' : '+'}${fmtMoney(Math.abs(salaryDelta))}`} sub={`In ${fmtMoney(verdict.costReceived)} · Out ${fmtMoney(verdict.costSent)}`} tone={salaryDelta <= 0 ? 'pos' : 'neg'} />
            {receivedArbTotal > 0 && (
              <Stat label="3yr arb cost (in)" value={fmtMoney(receivedArbTotal)} sub={sentArbTotal > 0 ? `vs ${fmtMoney(sentArbTotal)} out` : 'proj. controlled cost'} tone="neutral" />
            )}
          </div>
        </div>
      ) : (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-dashed border-ink-700 px-3 py-2.5 text-[11px] text-ink-600">
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
        </div>
        <div>
          <div className="mb-1.5 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-positive-400">
            ▶ {yourBref} receives
          </div>
          <BasketCard title={`${yourBref} receives`} team={partnerTeam} players={receivingPlayers}
            onRemove={id => setReceivedIds(p => p.filter(x => x !== id))} emptyHint="Pick from partner roster below." />
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

// ── main ───────────────────────────────────────────────────────────────────────

export default function WarRoom() {
  const active = useIdentityStore(s => s.activeTeam)
  const [yourPayload, setYourPayload] = useState<TeamPayload | null>(null)
  const [partnerBref, setPartnerBref] = useState<string | null>(null)
  const [partnerPayload, setPartnerPayload] = useState<TeamPayload | null>(null)

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

  const indexTeam = warRoomIndex.teams.find(t => t.code === active)
  if (!indexTeam) return (
    <div className="mx-auto max-w-[1480px] px-6 py-10 font-mono text-[12px] text-ink-500">
      No data for {active}.
    </div>
  )

  const headroom = indexTeam.payrollHeadroom
  const ctx = yourPayload?.context

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
            <div className="font-mono text-[10px] text-ink-500">{indexTeam.division}</div>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="font-mono text-right text-[10px] text-ink-600">
            <div>{warRoomIndex.season} SEASON · {warRoomIndex.asOfGames} GP</div>
            <div className="text-ink-700">blend w₂₀₂₆={warRoomIndex.blendWeight.toFixed(2)}</div>
          </div>
          <div className="flex items-center gap-1.5 rounded-md border border-ink-700 bg-ink-900 px-2.5 py-1.5">
            <PulseDot color="bg-positive-500" />
            <span className="font-mono text-[9px] font-semibold text-positive-400">LIVE</span>
          </div>
        </div>
      </div>

      {/* Heuristic banner */}
      <div className="mb-5 flex items-center gap-2 rounded border border-ink-700/50 bg-ink-900/40 px-3 py-1.5">
        <Info className="h-3 w-3 shrink-0 text-ink-600" />
        <span className="font-mono text-[10px] text-ink-600">
          Heuristic layer — pre-model. In-season stats shrunk toward 2025 prior. Contextual posteriors: Phase 2.
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[240px_1fr]">
        {/* Left: league board */}
        <aside className="lg:sticky lg:top-4 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto">
          <div className="mb-2 font-mono text-[8px] font-semibold uppercase tracking-[0.25em] text-ink-600">
            30-team board · click to analyze
          </div>
          <LeagueTicker yourBref={active} partnerBref={partnerBref} onSelect={setPartnerBref} />
        </aside>

        {/* Right: main intel + workshop */}
        <div className="min-w-0 space-y-4">
          {/* Your team intel */}
          <AnimatePresence mode="wait">
            {yourPayload ? (
              <motion.div key={active} initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
                {/* Posture banner */}
                <PostureBanner
                  posture={indexTeam.windowPosture}
                  rationale={ctx?.postureRationale ?? ''}
                />

                {/* Stats strip */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
                    <LiveStat label="Wins" value={indexTeam.w} tone="pos" />
                  </div>
                  <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
                    <LiveStat label="Losses" value={indexTeam.l} tone="neg" />
                  </div>
                  <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
                    <LiveStat
                      label="Games back"
                      value={indexTeam.gamesBack}
                      decimals={1}
                      tone={indexTeam.gamesBack === 0 ? 'pos' : indexTeam.gamesBack > 8 ? 'neg' : 'neutral'}
                      sub={indexTeam.gamesBack === 0 ? 'Division leader' : undefined}
                    />
                  </div>
                  <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
                    <LiveStat
                      label="Win %"
                      value={indexTeam.winPct * 1000}
                      decimals={0}
                      prefix="."
                      tone={indexTeam.winPct > 0.5 ? 'pos' : indexTeam.winPct < 0.42 ? 'neg' : 'neutral'}
                    />
                  </div>
                </div>

                {/* Payroll gauge */}
                <PayrollGauge
                  committed={indexTeam.payrollCommitted}
                  threshold={warRoomIndex.cbtThreshold}
                  headroom={headroom}
                />

                {/* Commitments + radar side by side */}
                <div className="grid gap-4 md:grid-cols-2">
                  {ctx && ctx.expiringContracts.length > 0 && (
                    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
                      <div className="mb-3 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">
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
                            <span className="truncate text-[11px] text-ink-300">{c.player}</span>
                            {c.position && (
                              <span className="shrink-0 rounded bg-ink-800 px-1 py-0.5 font-mono text-[9px] text-ink-500">
                                {c.position}
                              </span>
                            )}
                            <span className="font-mono shrink-0 text-[11px] tabular text-ink-400">
                              {money(c.capHit)}
                            </span>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  )}

                  <PositionRadar
                    holes={yourPayload.holes}
                    surpluses={yourPayload.surpluses}
                    posture={indexTeam.windowPosture}
                  />
                </div>

                {/* Holes board */}
                <HolesBoard
                  holes={yourPayload.holes}
                  surpluses={yourPayload.surpluses}
                  cite={yourPayload.holes[0]?.citation ?? ctx?.citation ?? { label: '', detail: '' }}
                />

                {/* Partner panel */}
                <AnimatePresence>
                  {partnerBref && (
                    <PartnerPanel
                      key={partnerBref}
                      bref={partnerBref}
                      payload={partnerPayload}
                      onClose={() => setPartnerBref(null)}
                    />
                  )}
                </AnimatePresence>

                {/* Phase 2 slots — only when no partner selected */}
                {!partnerBref && (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="rounded-lg border border-dashed border-ink-700 bg-ink-900/30 p-4 opacity-70">
                      <div className="mb-2 flex items-center gap-2 font-mono text-[11px] font-semibold text-ink-300">
                        <Sparkles className="h-4 w-4 text-accent-400" />Buy-low radar
                        <span className="chip chip-accent text-[9px]">Phase 2</span>
                      </div>
                      <p className="text-[11px] leading-relaxed text-ink-500">
                        League-wide stuff-to-results mismatches ranked by mispricing, filtered to your needs.
                      </p>
                    </div>
                    <div className="rounded-lg border border-dashed border-ink-700 bg-ink-900/30 p-4 opacity-70">
                      <div className="mb-2 flex items-center gap-2 font-mono text-[11px] font-semibold text-ink-300">
                        <Target className="h-4 w-4 text-accent-400" />Deals that clear
                        <span className="chip chip-accent text-[9px]">Phase 2</span>
                      </div>
                      <p className="text-[11px] leading-relaxed text-ink-500">
                        Generated scenarios intersecting your holes with sellers' surplus under payroll + control constraints.
                      </p>
                    </div>
                  </div>
                )}
              </motion.div>
            ) : (
              <div className="flex items-center justify-center py-20 font-mono text-[11px] text-ink-600">
                Loading {active} intel…
              </div>
            )}
          </AnimatePresence>

          {/* Trade workshop */}
          <AnimatePresence>
            {partnerBref && (
              <TradeWorkshop key={`ws-${partnerBref}`} yourBref={active} partnerBref={partnerBref} />
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
