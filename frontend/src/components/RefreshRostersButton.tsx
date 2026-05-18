import { useState } from 'react'
import { RefreshCw, CheckCircle2, AlertCircle, Info, Terminal } from 'lucide-react'
import { refreshRostersLive, type RefreshProgress } from '../lib/refreshRosters'
import { useRosterStore, useRoster } from '../lib/rosterStore'
import { refreshFarmLive, type FarmRefreshProgress } from '../lib/refreshFarm'
import { useFarmStore, useFarmMeta } from '../lib/farmStore'

type Size = 'sm' | 'md'

export function RefreshRostersButton({ size = 'md' }: { size?: Size }) {
  const setLiveRoster = useRosterStore((s) => s.setLive)
  const setLiveFarm = useFarmStore((s) => s.setLive)
  const current = useRoster()
  const farmMeta = useFarmMeta()
  const [running, setRunning] = useState(false)
  const [stage, setStage] = useState<'idle' | 'roster' | 'farm' | 'done'>('idle')
  const [rosterProg, setRosterProg] = useState<RefreshProgress>({ phase: 'idle', teamsDone: 0, teamsTotal: 30, playersDone: 0, playersTotal: 0 })
  const [farmProg, setFarmProg] = useState<FarmRefreshProgress>({ phase: 'idle', chunksDone: 0, chunksTotal: 0, playersDone: 0, playersTotal: 0, moved: 0 })
  const [error, setError] = useState<string | null>(null)
  const [movedTotal, setMovedTotal] = useState<number | null>(null)
  const [justFinishedAt, setJustFinishedAt] = useState<string | null>(null)
  const [showHint, setShowHint] = useState(false)

  async function run() {
    if (running) return
    setRunning(true)
    setError(null)
    setMovedTotal(null)
    setJustFinishedAt(null)
    setStage('roster')
    try {
      const r = await refreshRostersLive(setRosterProg)
      setLiveRoster(r)
      setStage('farm')
      const f = await refreshFarmLive(farmMeta.season, setFarmProg)
      setLiveFarm({ refreshed_at: new Date().toISOString(), season: farmMeta.season, teams: f.teams })
      setMovedTotal(f.moved)
      setStage('done')
      setJustFinishedAt(new Date().toISOString())
      setTimeout(() => setJustFinishedAt(null), 6000)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const lastSyncLabel = new Date(current.refreshed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
  const farmSyncLabel = new Date(farmMeta.refreshed_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })

  const detail = (() => {
    if (stage === 'roster') {
      if (rosterProg.phase === 'rosters') return `MLB · rosters ${rosterProg.teamsDone}/${rosterProg.teamsTotal} teams`
      if (rosterProg.phase === 'people') return `MLB · bios ${rosterProg.playersDone}/${rosterProg.playersTotal}`
      if (rosterProg.phase === 'merging') return 'MLB · merging…'
    }
    if (stage === 'farm') {
      if (farmProg.phase === 'affiliates') return 'Farm · pulling 2026 affiliate map'
      if (farmProg.phase === 'current-team') return `Farm · currentTeam ${farmProg.playersDone}/${farmProg.playersTotal}`
      if (farmProg.phase === 'rebucketing') return 'Farm · re-bucketing'
    }
    return ''
  })()

  const padX = size === 'sm' ? 'px-2' : 'px-3'
  const padY = size === 'sm' ? 'py-1' : 'py-1.5'
  const text = size === 'sm' ? 'text-[11px]' : 'text-[12px]'

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <button
          onClick={run}
          disabled={running}
          title="Live pull: MLB Stats API rosters + currentTeam re-bucketing for all 5K+ farm players"
          className={`group inline-flex items-center gap-1.5 rounded-md border border-ink-700 ${padX} ${padY} ${text} font-medium text-ink-200 transition-colors hover:border-accent-500/60 hover:text-ink-100 disabled:cursor-not-allowed disabled:text-ink-400`}
        >
          <RefreshCw className={`h-3 w-3 ${running ? 'animate-spin text-accent-400' : ''}`} />
          {running ? 'Refreshing…' : 'Refresh data'}
        </button>
        <button
          onClick={() => setShowHint((v) => !v)}
          title="What gets refreshed"
          className="grid h-6 w-6 place-items-center rounded-md border border-ink-700 text-ink-400 transition-colors hover:border-ink-500 hover:text-ink-200"
        >
          <Info className="h-3 w-3" />
        </button>
        <div className={`hidden flex-col leading-tight md:flex ${text}`}>
          {error ? (
            <span className="inline-flex items-center gap-1 text-negative-500">
              <AlertCircle className="h-3 w-3" /> {error}
            </span>
          ) : justFinishedAt ? (
            <span className="inline-flex items-center gap-1 text-positive-500">
              <CheckCircle2 className="h-3 w-3" />
              {current.player_count} MLB · {movedTotal != null ? `${movedTotal} farm movers` : 'farm re-bucketed'} · just now
            </span>
          ) : running ? (
            <span className="text-ink-300">{detail}</span>
          ) : (
            <span className="text-ink-400">
              MLB sync {lastSyncLabel}{farmMeta.source === 'live' ? ` · farm ${farmSyncLabel}` : ''}
            </span>
          )}
        </div>
      </div>
      {showHint && (
        <div className="card max-w-[520px] p-3 text-[11px] leading-relaxed text-ink-300">
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">What this button refreshes</div>
          <ul className="ml-4 list-disc space-y-1 marker:text-ink-500">
            <li><strong className="text-ink-100">Live</strong> · 40-man rosters (30 teams) — MLB Stats API</li>
            <li><strong className="text-ink-100">Live</strong> · Bio data for all 1.3K MLB players</li>
            <li><strong className="text-ink-100">Live</strong> · currentTeam for all 5.5K farm players (catches trades + promotions)</li>
            <li><strong className="text-ink-100">Live</strong> · 2026 affiliate map (re-buckets farm by current parent org)</li>
            <li><strong className="text-ink-100">Live</strong> · Player jersey, position, status (active / IL15 / etc.)</li>
            <li className="text-ink-400">Spotrac contracts (cap_hit, status, service time) — DB-only, see below</li>
            <li className="text-ink-400">MLB awards (MVP, Cy, SS, GG, ROY) — DB-only</li>
            <li className="text-ink-400">MiLB aggregate stats (PA-weighted OPS, IP-weighted ERA) — DB-only</li>
          </ul>
          <div className="mt-2 flex items-start gap-2 rounded-md border border-ink-700 bg-ink-950/80 p-2 mono text-[10.5px] text-ink-300">
            <Terminal className="mt-0.5 h-3 w-3 shrink-0 text-accent-400" />
            <div>
              <div className="text-ink-400">Full DB resync (Spotrac, awards, MiLB stats):</div>
              <div className="mt-0.5 text-ink-100">uv run python scripts/refresh_rosters.py</div>
              <div className="text-ink-100">uv run python scripts/export_org_profiles.py</div>
              <div className="text-ink-100">uv run python scripts/export_player_profiles.py</div>
              <div className="text-ink-100">uv run python scripts/export_farm.py</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
