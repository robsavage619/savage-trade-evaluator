import { blindSpots, flagsAsOf } from '../lib/contractFlags'

/** Names the players in a trade whose contract or availability the forecast cannot see. */
export function ForecastBlindSpots({
  players,
  className = '',
}: { players: readonly { mlb_player_id: number; name: string }[]; className?: string }) {
  const spots = blindSpots(players)
  if (spots.length === 0) return null
  return (
    <div className={`rounded border border-accent-500/30 bg-accent-500/5 px-2.5 py-2 ${className}`}>
      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-accent-400">
        Not in this forecast · check by hand
      </div>
      <ul className="mt-1 space-y-0.5 text-[11px] text-ink-200">
        {spots.map(s => (
          <li key={s.name}>
            <span className="font-semibold">{s.name}</span>
            <span className="text-ink-400"> · {s.flags.map(f => f.label).join(' · ')}</span>
          </li>
        ))}
      </ul>
      <div className="mt-1 font-mono text-[9px] text-ink-500">
        Contracts as of {flagsAsOf.contracts}; roster and injury status as of {flagsAsOf.roster}.
      </div>
    </div>
  )
}
