import type { DevSystem as DevSystemType } from '../../data/warroom/types'
import { SectionHeader } from './primitives'

const DEV_SYSTEM_CITE = {
  label: 'Dev-System Fingerprint',
  detail:
    'Avg K% percentile rank lift for pitchers acquired by this org in trades (2015–2024 Statcast). ' +
    'Positive = org historically improves strikeout rate post-acquisition. ' +
    'Min 3 trades required. Source: statcast_pitch_movement × trade_acquired_pitcher_arsenal_features.',
}

const TARGETS_CITE = {
  label: 'Low-K Targets',
  detail:
    'Current MLB pitchers (2025) with K% percentile rank ≤35 who could benefit from this org\'s development fingerprint. ' +
    'Ranked by K% rank ascending (worst first). Source: statcast_pitcher_percentile_ranks.',
}

function KLiftBar({ avgKLift }: { avgKLift: number }) {
  // Normalise to approx [-40, +40] range seen in the data
  const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))
  const pct = clamp(((avgKLift + 40) / 80) * 100, 0, 100)
  const isPositive = avgKLift >= 0
  return (
    <div className="mt-1">
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-ink-800">
        <div
          className={`absolute inset-y-0 rounded-full transition-all ${isPositive ? 'bg-positive-400/70' : 'bg-negative-400/60'}`}
          style={{ left: '50%', width: `${Math.abs(pct - 50)}%`, transform: isPositive ? 'none' : 'translateX(-100%)' }}
        />
        <div className="absolute inset-y-0 w-px bg-ink-500" style={{ left: '50%' }} />
      </div>
      <div className="mt-0.5 flex justify-between font-mono text-[7px] text-ink-600">
        <span>−40</span>
        <span>0</span>
        <span>+40</span>
      </div>
    </div>
  )
}

export function DevSystem({ data }: { data: DevSystemType }) {
  const isTopTier = data.rank <= 5
  const isBottomTier = data.rank >= data.nOrgs - 2
  const rankColor = isTopTier
    ? 'text-positive-400'
    : isBottomTier
    ? 'text-negative-400'
    : 'text-ink-300'
  const liftColor = data.avgKLift >= 0 ? 'text-positive-400' : 'text-negative-400'

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
      <SectionHeader label="Dev-System Fingerprint" cite={DEV_SYSTEM_CITE} />

      {/* headline stats */}
      <div className="mt-3 flex flex-wrap gap-4">
        <div>
          <div className="font-mono text-[8px] uppercase tracking-widest text-ink-500">Avg K% Lift</div>
          <div className={`font-mono text-[22px] font-black leading-none tabular ${liftColor}`}>
            {data.avgKLift >= 0 ? '+' : ''}
            {data.avgKLift.toFixed(1)}
          </div>
          {data.stdKLift != null && (
            <div className="font-mono text-[8px] text-ink-600">±{data.stdKLift.toFixed(1)} std</div>
          )}
        </div>
        <div>
          <div className="font-mono text-[8px] uppercase tracking-widest text-ink-500">MLB Rank</div>
          <div className={`font-mono text-[22px] font-black leading-none tabular ${rankColor}`}>
            #{data.rank}
          </div>
          <div className="font-mono text-[8px] text-ink-600">of {data.nOrgs} orgs</div>
        </div>
        <div>
          <div className="font-mono text-[8px] uppercase tracking-widest text-ink-500">Sample</div>
          <div className="font-mono text-[22px] font-black leading-none tabular text-ink-300">
            {data.nTrades}
          </div>
          <div className="font-mono text-[8px] text-ink-600">trades</div>
        </div>
      </div>

      <KLiftBar avgKLift={data.avgKLift} />

      {/* low-K targets */}
      {data.topTargets.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 flex items-center gap-2">
            <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
              Low-K Targets
            </span>
            <span className="font-mono text-[8px] text-ink-600" title={TARGETS_CITE.detail}>
              2025 · K%rk ≤35
            </span>
          </div>
          <div className="space-y-1">
            {data.topTargets.slice(0, 6).map((t, i) => (
              <div key={i} className="flex items-center gap-2">
                <span className="w-36 shrink-0 font-mono text-[9px] text-ink-200 truncate">{t.playerName}</span>
                <span className="rounded bg-negative-500/10 px-1 py-px font-mono text-[8px] text-negative-400">
                  K%rk {t.kPctRank}
                </span>
                {t.whiffRank != null && (
                  <span className="rounded bg-ink-800 px-1 py-px font-mono text-[8px] text-ink-400">
                    whiff {t.whiffRank}
                  </span>
                )}
                {t.fbVelo != null && (
                  <span className="rounded bg-ink-800 px-1 py-px font-mono text-[8px] text-ink-400">
                    fb rk {t.fbVelo.toFixed(0)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
