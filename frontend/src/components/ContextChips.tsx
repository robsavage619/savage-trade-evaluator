import { Gauge, Coins, Trees, Target, Wand2 } from 'lucide-react'

type Chip = { icon: typeof Gauge; label: string; value: string; sub?: string }

export function ContextChips({ chips }: { chips: Chip[] }) {
  return (
    <div className="flex flex-col gap-2">
      {chips.map((c) => (
        <div key={c.label} className="card flex items-start gap-3 p-3">
          <div className="grid h-7 w-7 shrink-0 place-items-center rounded-md bg-ink-700 text-accent-400">
            <c.icon className="h-3.5 w-3.5" />
          </div>
          <div className="flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-[11px] uppercase tracking-[0.12em] text-ink-400">{c.label}</div>
              <div className="mono text-[12px] font-semibold tabular text-ink-100">{c.value}</div>
            </div>
            {c.sub ? <div className="mt-0.5 text-[11px] text-ink-400">{c.sub}</div> : null}
          </div>
        </div>
      ))}
    </div>
  )
}

export const CONTEXT_ICONS = { Gauge, Coins, Trees, Target, Wand2 }
