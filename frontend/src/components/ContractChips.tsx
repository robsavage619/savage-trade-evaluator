import { flagsFor } from '../lib/contractFlags'

const TONE = {
  warn: 'text-accent-400 bg-accent-500/10 border-accent-500/30',
  info: 'text-ink-300 bg-ink-700/50 border-ink-600/30',
}

/** Contract and availability facts for one player, as small chips with the detail on hover. */
export function ContractChips({ id }: { id: number }) {
  const flags = flagsFor(id)
  if (flags.length === 0) return null
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {flags.map(f => (
        <span
          key={f.label}
          title={f.detail}
          className={`mono rounded border px-1 py-0.5 text-[8px] font-semibold uppercase tracking-wider ${TONE[f.tone]}`}
        >
          {f.label}
        </span>
      ))}
    </div>
  )
}
