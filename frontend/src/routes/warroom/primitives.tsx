import { useEffect, useRef } from 'react'
import { animate } from 'framer-motion'
import { Info } from 'lucide-react'
import type { Citation } from '../../data/warroom/types'

// ── citation tooltip ─────────────────────────────────────────────────────────

export function Cite({ cite }: { cite: Citation }) {
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

export function SectionHeader({ label, cite }: { label: string; cite?: Citation }) {
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

export function AnimatedNumber({
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

export function PulseDot({ color }: { color: string }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${color}`} />
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
    </span>
  )
}
