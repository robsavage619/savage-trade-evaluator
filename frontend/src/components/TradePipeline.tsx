import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Search, Filter } from 'lucide-react'
import { PIPELINE, STATUS_LABELS, STATUS_TONES, type PipelineStatus } from '../data/pipeline'
import { TeamLogo } from './TeamLogo'

const STATUS_ORDER: PipelineStatus[] = ['hot', 'gm-call', 'exploring', 'cold', 'closed']

export function TradePipeline() {
  const params = useParams<{ id: string }>()
  const activeId = Number(params.id)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<PipelineStatus | 'all'>('all')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return PIPELINE.filter((e) => {
      if (statusFilter !== 'all' && e.status !== statusFilter) return false
      if (!q) return true
      return (
        e.shortLabel.toLowerCase().includes(q) ||
        e.primaryAcquirer.toLowerCase().includes(q) ||
        e.primarySender.toLowerCase().includes(q) ||
        e.ownerInitials.toLowerCase().includes(q)
      )
    })
  }, [query, statusFilter])

  const byStatus = useMemo(() => {
    const m = new Map<PipelineStatus, typeof PIPELINE>()
    for (const e of filtered) {
      if (!m.has(e.status)) m.set(e.status, [] as never)
      m.get(e.status)!.push(e)
    }
    return m
  }, [filtered])

  return (
    <aside className="card flex h-full flex-col overflow-hidden">
      <div className="border-b border-ink-700 p-3">
        <div className="mb-2 flex items-center justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Pipeline</div>
            <div className="text-[13px] font-semibold text-ink-100">Workable trades</div>
          </div>
          <span className="chip">{PIPELINE.length} active</span>
        </div>
        <div className="relative mb-2">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search players, teams, owner…"
            className="w-full rounded-md border border-ink-700 bg-ink-800/80 py-1.5 pl-7 pr-2 text-[12px] text-ink-100 placeholder:text-ink-400 focus:border-accent-500/50 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1 overflow-x-auto">
          <button
            onClick={() => setStatusFilter('all')}
            className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
              statusFilter === 'all' ? 'border-ink-500 bg-ink-700 text-ink-100' : 'border-ink-700 text-ink-400 hover:text-ink-200'
            }`}
          >
            all
          </button>
          {STATUS_ORDER.map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                statusFilter === s ? STATUS_TONES[s] : 'border-ink-700 text-ink-400 hover:text-ink-200'
              }`}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {STATUS_ORDER.map((status) => {
          const list = byStatus.get(status)
          if (!list?.length) return null
          return (
            <div key={status} className="mb-3">
              <div className="mb-1 flex items-center justify-between px-1.5">
                <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
                  <Filter className="h-2.5 w-2.5" />
                  {STATUS_LABELS[status]}
                </div>
                <span className="mono text-[10px] text-ink-500">{list.length}</span>
              </div>
              <div className="space-y-1.5">
                {list.map((e) => {
                  const active = activeId === e.tradeId
                  return (
                    <Link
                      key={e.tradeId}
                      to={`/trade/${e.tradeId}`}
                      className={`group block rounded-md border px-2.5 py-2 transition-colors ${
                        active
                          ? 'border-accent-500/50 bg-accent-500/10'
                          : 'border-transparent bg-ink-800/40 hover:border-ink-600 hover:bg-ink-800'
                      }`}
                    >
                      <div className="mb-1 flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <TeamLogo team={e.primarySender} size={14} />
                          <span className="text-[10px] text-ink-400">→</span>
                          <TeamLogo team={e.primaryAcquirer} size={14} />
                          <span className={`ml-1 text-[12px] font-semibold ${active ? 'text-ink-100' : 'text-ink-200 group-hover:text-ink-100'}`}>
                            {e.shortLabel}
                          </span>
                        </div>
                        <span className={`chip ${STATUS_TONES[e.status]}`}>{STATUS_LABELS[e.status]}</span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-ink-400">
                        <span className="mono">{e.asOf}</span>
                        <span className="flex items-center gap-1">
                          <span className="grid h-3.5 w-3.5 place-items-center rounded-full bg-ink-700 text-[8px] font-bold text-ink-200">
                            {e.ownerInitials}
                          </span>
                        </span>
                      </div>
                    </Link>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
      <div className="border-t border-ink-700 p-3 text-[10px] text-ink-400">
        <span className="mono">Live pipeline · auto-refreshed from MLB Stats API</span>
      </div>
    </aside>
  )
}
