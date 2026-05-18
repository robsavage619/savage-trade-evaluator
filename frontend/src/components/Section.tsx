import type { ReactNode } from 'react'

type Props = {
  eyebrow?: string
  title: string
  hint?: string
  right?: ReactNode
  children: ReactNode
  className?: string
}

export function Section({ eyebrow, title, hint, right, children, className }: Props) {
  return (
    <section className={`mb-6 ${className ?? ''}`}>
      <header className="mb-3 flex items-end justify-between gap-4">
        <div>
          {eyebrow ? (
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">{eyebrow}</div>
          ) : null}
          <h2 className="text-[15px] font-semibold tracking-tight text-ink-100">{title}</h2>
          {hint ? <div className="mt-1 text-[12px] text-ink-400">{hint}</div> : null}
        </div>
        {right}
      </header>
      {children}
    </section>
  )
}

export function Stat({ label, value, sub, tone = 'neutral' }: { label: string; value: string; sub?: string; tone?: 'neutral' | 'pos' | 'neg' }) {
  const toneCls = tone === 'pos' ? 'text-positive-500' : tone === 'neg' ? 'text-negative-500' : 'text-ink-100'
  return (
    <div>
      <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-ink-400">{label}</div>
      <div className={`mono mt-0.5 text-[22px] font-semibold tabular leading-none ${toneCls}`}>{value}</div>
      {sub ? <div className="mt-1 text-[11px] text-ink-400">{sub}</div> : null}
    </div>
  )
}
