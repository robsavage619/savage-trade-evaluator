import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search, Plus, AlertCircle, BadgePlus, X, User } from 'lucide-react'
import type { CurrentPlayer, CurrentTeam } from '../data/players'
import { useRoster, useTeamsByBref } from '../lib/rosterStore'
import { TeamLogo } from './TeamLogo'
import { fmtMoney } from '../lib/format'
import { forecastArb, parseArbClass, isControlled } from '../lib/arbForecast'
import type { ArbClass } from '../lib/arbForecast'

const ARB_LABEL: Record<ArbClass, string> = {
  'pre-arb': 'PRE-ARB',
  arb1: 'ARB 1',
  arb2: 'ARB 2',
  arb3: 'ARB 3',
  fa: 'FA',
}
const ARB_COLOR: Record<ArbClass, string> = {
  'pre-arb': 'text-positive-400 border-positive-500/40 bg-positive-500/10',
  arb1: 'text-accent-300 border-accent-500/40 bg-accent-500/10',
  arb2: 'text-accent-400 border-accent-500/30 bg-accent-500/8',
  arb3: 'text-ink-300 border-ink-600 bg-ink-800/60',
  fa: 'text-ink-500 border-ink-700 bg-transparent',
}
const CTRL_YEARS: Record<ArbClass, number> = {
  'pre-arb': 4, arb1: 3, arb2: 2, arb3: 1, fa: 0,
}

function ArbBadge({ cls }: { cls: ArbClass }) {
  if (cls === 'fa') return null
  const years = CTRL_YEARS[cls]
  return (
    <span className={`inline-flex items-center gap-0.5 rounded border px-1 py-px font-mono text-[8.5px] font-bold leading-none ${ARB_COLOR[cls]}`}>
      {ARB_LABEL[cls]}
      {years > 0 && <span className="opacity-70">·{years}Y</span>}
    </span>
  )
}

type Props = {
  /** Filter to this team's roster. When 'all', all 30 teams visible. */
  team: string | 'all'
  onPickTeam: (bref: string | 'all') => void
  onAdd: (player: CurrentPlayer, team: CurrentTeam) => void
  selectedIds: Set<number>
  title: string
  hint?: string
}

type PosFilter = 'all' | 'pitcher' | 'hitter'
type StatusFilter = 'all' | 'active' | 'injured'
type CtrlFilter = 'all' | 'ctrl' | 'fa'

export function PlayerPicker({ team, onPickTeam, onAdd, selectedIds, title, hint }: Props) {
  const [query, setQuery] = useState('')
  const [pos, setPos] = useState<PosFilter>('all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [ctrl, setCtrl] = useState<CtrlFilter>('all')
  const roster = useRoster()
  const teamsByBref = useTeamsByBref()

  const list = useMemo(() => {
    const q = query.trim().toLowerCase()
    const teams = team === 'all' ? roster.teams : [teamsByBref[team]].filter(Boolean) as CurrentTeam[]
    const flat: Array<{ player: CurrentPlayer; team: CurrentTeam; arbClass: ArbClass }> = []
    for (const t of teams) {
      for (const p of t.players) {
        if (selectedIds.has(p.mlb_player_id)) continue
        if (pos === 'pitcher' && p.position_code !== '1') continue
        if (pos === 'hitter' && p.position_code === '1') continue
        if (status === 'active' && p.status_code !== 'A') continue
        if (status === 'injured' && !['D7', 'D10', 'D15', 'D60'].includes(p.status_code ?? '')) continue
        if (q && !`${p.name} ${p.position_abbr ?? ''}`.toLowerCase().includes(q)) continue
        const arbClass = parseArbClass(p.contract_status)
        if (ctrl === 'ctrl' && !isControlled(arbClass)) continue
        if (ctrl === 'fa' && isControlled(arbClass)) continue
        flat.push({ player: p, team: t, arbClass })
      }
    }
    // Sort by last_war desc (best first)
    flat.sort((a, b) => (b.player.last_war ?? -10) - (a.player.last_war ?? -10))
    return flat.slice(0, 200)
  }, [query, pos, status, ctrl, team, selectedIds, roster, teamsByBref])

  return (
    <div className="card flex h-full flex-col overflow-hidden">
      <div className="border-b border-ink-700 p-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">{title}</div>
            {hint && <div className="text-[11px] text-ink-400">{hint}</div>}
          </div>
          <select
            value={team}
            onChange={(e) => onPickTeam(e.target.value)}
            className="rounded-md border border-ink-700 bg-ink-800 px-2 py-1 text-[11px] text-ink-100 focus:border-accent-500/50 focus:outline-none"
          >
            <option value="all">All 30 teams</option>
            {roster.teams.map((t) => (
              <option key={t.bref} value={t.bref}>{t.bref} · {t.name}</option>
            ))}
          </select>
        </div>
        <div className="relative mt-2">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search player or position…"
            className="w-full rounded-md border border-ink-700 bg-ink-800/80 py-1.5 pl-7 pr-2 text-[12px] text-ink-100 placeholder:text-ink-400 focus:border-accent-500/50 focus:outline-none"
          />
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {(['all', 'pitcher', 'hitter'] as PosFilter[]).map((p) => (
            <button key={p} onClick={() => setPos(p)}
              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${pos === p ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-400 hover:text-ink-200'}`}
            >{p}</button>
          ))}
          <span className="mx-0.5 h-3 w-px bg-ink-700" />
          {(['all', 'active', 'injured'] as StatusFilter[]).map((s) => (
            <button key={s} onClick={() => setStatus(s)}
              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${status === s ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-400 hover:text-ink-200'}`}
            >{s}</button>
          ))}
          <span className="mx-0.5 h-3 w-px bg-ink-700" />
          {([['all', 'ALL'], ['ctrl', 'CTRL'], ['fa', 'FA']] as [CtrlFilter, string][]).map(([v, lbl]) => (
            <button key={v} onClick={() => setCtrl(v)}
              className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${ctrl === v ? 'border-positive-500/50 bg-positive-500/10 text-positive-400' : 'border-ink-700 text-ink-400 hover:text-ink-200'}`}
            >{lbl}</button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {list.length === 0 ? (
          <div className="grid h-full place-items-center p-6 text-[12px] text-ink-400">No players match.</div>
        ) : (
          <ul className="divide-y divide-ink-700/50">
            {list.map(({ player: p, team: t, arbClass }) => {
              const injured = !!p.status_code && p.status_code.startsWith('D')
              const arb = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
              const yr1 = arb.projections[0]
              return (
                <li key={p.mlb_player_id} className="group flex items-stretch hover:bg-ink-800/60">
                  <button
                    onClick={() => onAdd(p, t)}
                    className="flex flex-1 items-center gap-2.5 px-3 py-2 text-left transition-colors"
                    title="Add to basket"
                  >
                    <TeamLogo team={t.bref} size={20} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-[12px] font-semibold text-ink-100">{p.name}</span>
                        <ArbBadge cls={arbClass} />
                        {injured && (
                          <span className="chip chip-neg mono">
                            <AlertCircle className="h-2.5 w-2.5" /> {p.status_code}
                          </span>
                        )}
                      </div>
                      <div className="mono text-[10px] tabular text-ink-400">
                        {p.position_abbr ?? '—'}
                        {p.age != null ? ` · ${p.age}y` : ''}
                        {p.pitch_hand ? ` · ${p.pitch_hand}HP` : ''}
                        {p.bat_side ? ` · ${p.bat_side}HB` : ''}
                        {p.last_war != null ? ` · ${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)} WAR ${p.last_year}` : ''}
                        {isControlled(arbClass)
                          ? ` · ${fmtMoney(yr1)} next`
                          : p.cap_hit != null ? ` · ${fmtMoney(p.cap_hit)}` : p.last_salary != null ? ` · ${fmtMoney(p.last_salary)}` : ''}
                      </div>
                    </div>
                    <Plus className="h-3.5 w-3.5 text-ink-400 transition-colors group-hover:text-accent-400" />
                  </button>
                  <Link
                    to={`/player/${p.mlb_player_id}`}
                    className="grid w-8 place-items-center border-l border-ink-700/50 text-ink-400 transition-colors hover:bg-ink-700 hover:text-accent-300"
                    title="Open player profile"
                  >
                    <User className="h-3.5 w-3.5" />
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      <div className="border-t border-ink-700 px-3 py-2 text-[10px] text-ink-400">
        <span className="mono">{list.length} of {team === 'all' ? roster.player_count : teamsByBref[team]?.roster_count ?? 0} · click <BadgePlus className="inline h-2.5 w-2.5" /> to add</span>
      </div>
    </div>
  )
}

export function BasketCard({
  title,
  team,
  players,
  onRemove,
  emptyHint,
}: {
  title: string
  team: CurrentTeam | null
  players: CurrentPlayer[]
  onRemove: (id: number) => void
  emptyHint: string
}) {
  return (
    <div className="card flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-ink-700 p-3">
        <div className="flex items-center gap-2">
          {team ? <TeamLogo team={team.bref} size={22} /> : null}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">{title}</div>
            <div className="text-[13px] font-semibold text-ink-100">{team?.name ?? '—'}</div>
          </div>
        </div>
        <span className="chip mono">{players.length} player{players.length === 1 ? '' : 's'}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {players.length === 0 ? (
          <div className="grid h-full place-items-center p-6 text-center text-[12px] text-ink-400">{emptyHint}</div>
        ) : (
          <ul className="space-y-1.5">
            {players.map((p) => {
              const arbClass = parseArbClass(p.contract_status)
              const arb = forecastArb(p.contract_status, p.last_war, p.cap_hit, p.position_abbr)
              return (
              <li key={p.mlb_player_id} className="flex items-center justify-between gap-2 rounded-md border border-ink-700 bg-ink-800/40 p-2 hover:border-ink-600">
                <Link to={`/player/${p.mlb_player_id}`} className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-[12.5px] font-semibold text-ink-100 hover:text-accent-300">{p.name}</span>
                    <ArbBadge cls={arbClass} />
                  </div>
                  <div className="mono text-[10px] tabular text-ink-400">
                    {p.position_abbr ?? '—'}
                    {p.age != null ? ` · ${p.age}y` : ''}
                    {p.last_war != null ? ` · ${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)} WAR` : ''}
                    {isControlled(arbClass)
                      ? ` · ${fmtMoney(arb.projections[0])} next · ${fmtMoney(arb.totalCost3yr)} 3yr`
                      : p.cap_hit != null ? ` · ${fmtMoney(p.cap_hit)}` : p.last_salary != null ? ` · ${fmtMoney(p.last_salary)}` : ''}
                  </div>
                </Link>
                <button
                  onClick={() => onRemove(p.mlb_player_id)}
                  className="rounded-md p-1 text-ink-400 transition-colors hover:bg-negative-500/10 hover:text-negative-500"
                  aria-label="remove"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            )})}
          </ul>
        )}
      </div>
    </div>
  )
}
