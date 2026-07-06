import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import type { Citation, WindowPosture } from '../../data/warroom/types'
import type { ArbClass } from '../../lib/arbForecast'

// ── posture config ───────────────────────────────────────────────────────────

export const POSTURE: Record<WindowPosture, {
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

export const SEVERITY_COLOR: Record<string, string> = {
  critical: '#ff5d73',
  warning: '#ff8a3d',
  ok: '#364264',
}

export const SEVERITY_WEIGHT: Record<string, number> = { critical: 3, warning: 1.5, ok: 0.5 }

export const DIVISIONS = ['AL East', 'AL Central', 'AL West', 'NL East', 'NL Central', 'NL West']

// ── helpers ──────────────────────────────────────────────────────────────────

export function money(v: number) {
  const neg = v < 0; const a = Math.abs(v)
  const s = a >= 1_000_000 ? `$${(a / 1_000_000).toFixed(1)}M` : `$${(a / 1_000).toFixed(0)}K`
  return neg ? `−${s}` : s
}

// ── playoff probability ───────────────────────────────────────────────────────

/** Logistic heuristic — 12/30 teams make playoffs; adjusted for win% and games back. */
export function computePlayoffProb(w: number, l: number, gamesBack: number): number {
  const total = w + l
  if (total === 0) return 0.4
  const winPct = w / total
  const logit = (winPct - 0.5) * 12 - gamesBack * 0.12 - 0.25
  return Math.max(0.02, Math.min(0.97, 1 / (1 + Math.exp(-logit))))
}

// ── shared citations ──────────────────────────────────────────────────────────

export const HOLE_SCORE_CITE: Citation = {
  label: 'Hole Score',
  detail: 'WAR deficit vs a replacement-level player at this position. −2.2 = this slot is costing you ~2 wins. Critical = needs an upgrade at the deadline.',
}
export const SURPLUS_WAR_CITE: Citation = {
  label: 'Tradeable Surplus',
  detail: 'WAR production above salary cost over remaining control years. Positive surplus = cost-controlled asset. This is the currency of any trade.',
}

// ── arb class helpers ─────────────────────────────────────────────────────────

export function advanceArbClass(cls: ArbClass, years: number): ArbClass {
  const seq: ArbClass[] = ['pre-arb', 'arb1', 'arb2', 'arb3', 'fa']
  const i = seq.indexOf(cls)
  return seq[Math.min(i + years, seq.length - 1)]
}

export const ARB_CLASS_LABEL: Record<ArbClass, string> = {
  'pre-arb': 'PRE', arb1: 'A1', arb2: 'A2', arb3: 'A3', fa: 'FA',
}
export const ARB_CLASS_COLOR: Record<ArbClass, string> = {
  'pre-arb': 'text-positive-400', arb1: 'text-accent-300',
  arb2: 'text-accent-400', arb3: 'text-ink-400', fa: 'text-ink-500',
}
