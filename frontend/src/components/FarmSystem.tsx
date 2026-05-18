import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Sprout, Star, ChevronRight, Trophy, Crosshair, Sparkles, ArrowRightLeft } from 'lucide-react'
import { LEVEL_LABELS, LEVEL_ORDER, type FarmPlayer, type FarmTeam } from '../data/farm'
import { scoutGrade, gradeTone, gradeLabel } from '../lib/prospectGrade'

type Props = { farm: FarmTeam | undefined; themeColor: string }

export function FarmSystem({ farm, themeColor }: Props) {
  const milbCount = LEVEL_ORDER.reduce((a, lv) => a + (farm?.levels[lv]?.length ?? 0), 0)
  if (!farm || milbCount === 0) {
    return (
      <div className="card flex items-center gap-3 p-5">
        <div className="grid h-10 w-10 place-items-center rounded-md bg-ink-700 text-ink-400">
          <Sprout className="h-5 w-5" />
        </div>
        <div className="text-[12px] text-ink-400">No farm data on file for this org.</div>
      </div>
    )
  }

  // Default to deepest populated level
  const defaultLevel = LEVEL_ORDER.find((lv) => (farm.levels[lv]?.length ?? 0) > 0) ?? 'AAA'
  const [activeLevel, setActiveLevel] = useState<FarmPlayer['level']>(defaultLevel)
  const [view, setView] = useState<'all' | 'hitters' | 'pitchers'>('all')
  const [sortBy, setSortBy] = useState<'grade' | 'stat'>('grade')
  const players = farm.levels[activeLevel] ?? []

  // Compute grades once per level for stable sort
  const withGrade = useMemo(() => players.map((p) => ({ p, grade: scoutGrade(p) })), [players])
  const hitters = withGrade.filter((x) => !x.p.is_pitcher)
  const pitchers = withGrade.filter((x) => x.p.is_pitcher)
  if (sortBy === 'grade') {
    hitters.sort((a, b) => b.grade - a.grade)
    pitchers.sort((a, b) => b.grade - a.grade)
  } else {
    hitters.sort((a, b) => (b.p.ops_pa_weighted ?? 0) - (a.p.ops_pa_weighted ?? 0))
    pitchers.sort((a, b) => (a.p.era_ip_weighted ?? 99) - (b.p.era_ip_weighted ?? 99))
  }

  // Org top-prospects ranked by scout grade (MiLB only — MLB-rostered show in
  // the 40-man section above; we want this panel to be the pure farm view).
  const orgTopGrades = useMemo(() => {
    return LEVEL_ORDER.flatMap((lv) => farm.levels[lv] ?? [])
      .map((p) => ({ p, grade: scoutGrade(p) }))
      .sort((a, b) => b.grade - a.grade)
      .slice(0, 10)
  }, [farm])

  // Org top-5 (sorted by quality across all levels, weighted by performance)
  const orgTopHitters = useMemo(() => {
    return Object.values(farm.levels).flat()
      .filter((p) => !p.is_pitcher && (p.pa ?? 0) >= 50 && p.ops_pa_weighted != null)
      .sort((a, b) => (b.ops_pa_weighted ?? 0) - (a.ops_pa_weighted ?? 0))
      .slice(0, 6)
  }, [farm])

  const orgTopPitchers = useMemo(() => {
    return Object.values(farm.levels).flat()
      .filter((p) => p.is_pitcher && (p.ip ?? 0) >= 20 && p.era_ip_weighted != null)
      .sort((a, b) => (a.era_ip_weighted ?? 99) - (b.era_ip_weighted ?? 99))
      .slice(0, 6)
  }, [farm])

  return (
    <div className="space-y-4">
      {/* Level tabs */}
      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-700 p-3">
          <div className="flex flex-wrap items-center gap-1">
            {LEVEL_ORDER.map((lv) => {
              const count = farm.levels[lv]?.length ?? 0
              if (count === 0) return null
              const active = lv === activeLevel
              return (
                <button
                  key={lv}
                  onClick={() => setActiveLevel(lv)}
                  className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                    active ? 'border-accent-500/50 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-300 hover:border-ink-500 hover:text-ink-100'
                  }`}
                >
                  <span>{lv}</span>
                  <span className="mono text-[10px] tabular text-ink-400">{count}</span>
                </button>
              )
            })}
            <span className="ml-2 text-[10px] uppercase tracking-[0.14em] text-ink-400">{LEVEL_LABELS[activeLevel]}</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              {(['all', 'hitters', 'pitchers'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                    view === v ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-400 hover:text-ink-200'
                  }`}
                >{v}</button>
              ))}
            </div>
            <span className="h-3 w-px bg-ink-700" />
            <div className="flex items-center gap-1">
              {(['grade', 'stat'] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSortBy(s)}
                  className={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                    sortBy === s ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-400 hover:text-ink-200'
                  }`}
                  title={s === 'grade' ? 'Sort by scout-grade proxy (20-80)' : 'Sort by raw OPS/ERA'}
                >sort: {s}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid gap-0 md:grid-cols-2">
          {(view === 'all' || view === 'hitters') && (
            <PlayerList title={sortBy === 'grade' ? 'Hitters · scout grade' : 'Hitters · top OPS'} icon={Star} themeColor={themeColor} players={hitters.slice(0, 12)} kind="hitter" />
          )}
          {(view === 'all' || view === 'pitchers') && (
            <PlayerList title={sortBy === 'grade' ? 'Pitchers · scout grade' : 'Pitchers · top ERA'} icon={Crosshair} themeColor={themeColor} players={pitchers.slice(0, 12)} kind="pitcher" />
          )}
        </div>
      </div>

      {/* Org top prospects by scout-grade proxy */}
      <div className="card p-4">
        <div className="mb-1 flex items-center gap-2">
          <Trophy className="h-3.5 w-3.5 text-accent-400" />
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Org top-10 prospects · scout-grade proxy</div>
        </div>
        <div className="mb-3 flex items-center gap-1.5 text-[10.5px] text-ink-400">
          <Sparkles className="h-3 w-3" />
          <span>Synthetic 20-80 grade: age vs typical-for-level + performance + reach. Anchor for V2 prospect model.</span>
        </div>
        <div className="grid gap-1.5 md:grid-cols-2">
          {orgTopGrades.map(({ p, grade }, i) => (
            <TopProspectRow key={p.mlb_player_id} player={p} rank={i + 1} grade={grade} themeColor={themeColor} />
          ))}
        </div>
        <div className="mt-3 flex items-center justify-between gap-2 text-[10px] text-ink-400">
          <span className="mono">{orgTopHitters.length}/{orgTopPitchers.length} qualified hitters/pitchers used elsewhere</span>
          <span className="mono">grade tiers: 70+ Top 100 · 60 Org top-10 · 55 above avg · 45 depth · &lt;45 filler</span>
        </div>
      </div>
    </div>
  )
}

function TopProspectRow({ player, rank, grade, themeColor }: { player: FarmPlayer; rank: number; grade: number; themeColor: string }) {
  const kind = player.is_pitcher ? 'pitcher' : 'hitter'
  const stat = kind === 'hitter' ? (player.ops_pa_weighted ?? 0).toFixed(3) : (player.era_ip_weighted ?? 0).toFixed(2)
  const sample = kind === 'hitter' ? `${player.pa ?? 0}pa` : `${player.ip ?? 0}ip`
  return (
    <Link to={`/player/${player.mlb_player_id}`} className="group flex items-center gap-2 rounded-md border border-ink-700 bg-ink-800/40 px-2.5 py-2 hover:border-accent-500/40 hover:bg-ink-800/60">
      <span className="mono w-5 text-right text-[10px] font-bold tabular text-ink-500">{rank}</span>
      <GradeChip grade={grade} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[12px] font-semibold text-ink-100 group-hover:text-accent-300">{player.name}</span>
          {player.moved_since_2024 && player.former_parent && (
            <span title={`Acquired from ${player.former_parent} since 2024`} className="chip chip-accent mono inline-flex items-center gap-0.5 px-1 py-0">
              <ArrowRightLeft className="h-2 w-2" />{player.former_parent}
            </span>
          )}
        </div>
        <div className="mono text-[10px] tabular text-ink-400">
          {player.position_abbr ?? '—'} · age {player.age ?? '?'} · <span className="text-accent-300">{player.level}</span>
          <span className="text-ink-500"> · {gradeLabel(grade)}</span>
        </div>
      </div>
      <div className="text-right">
        <div className="mono text-[11px] font-semibold tabular" style={{ color: themeColor }}>{stat}</div>
        <div className="mono text-[10px] tabular text-ink-400">{sample}</div>
      </div>
    </Link>
  )
}

function PlayerList({ players, title, icon: Icon, kind, themeColor }: { players: Array<{ p: FarmPlayer; grade: number }>; title: string; icon: React.ElementType; kind: 'hitter' | 'pitcher'; themeColor: string }) {
  return (
    <div>
      <div className="flex items-center gap-1.5 border-b border-ink-700/60 bg-ink-800/40 px-3 py-1.5 text-[10px] uppercase tracking-[0.12em] text-ink-400">
        <Icon className="h-3 w-3" />
        {title}
      </div>
      {players.length === 0 ? (
        <div className="grid place-items-center p-6 text-[12px] text-ink-500">No {kind}s at this level.</div>
      ) : (
        <ul className="divide-y divide-ink-700/40">
          {players.map(({ p, grade }) => (
            <li key={p.mlb_player_id}>
              <Link to={`/player/${p.mlb_player_id}`} className="group flex items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-ink-800/60">
                <GradeChip grade={grade} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-[12px] font-semibold text-ink-100 group-hover:text-accent-300">{p.name}</span>
                    {p.moved_since_2024 && p.former_parent && (
                      <span title={`Acquired from ${p.former_parent} since 2024`} className="chip chip-accent mono inline-flex items-center gap-0.5 px-1 py-0">
                        <ArrowRightLeft className="h-2 w-2" />{p.former_parent}
                      </span>
                    )}
                  </div>
                  <div className="mono text-[10px] tabular text-ink-400">
                    {p.position_abbr ?? '—'} · age {p.age ?? '?'}
                    {p.team_name ? ` · ${p.team_abbrev ?? p.team_name}` : ''}
                  </div>
                </div>
                <div className="text-right">
                  {kind === 'hitter' ? (
                    <>
                      <div className="mono text-[12px] font-semibold tabular" style={{ color: themeColor }}>{(p.ops_pa_weighted ?? 0).toFixed(3)}</div>
                      <div className="mono text-[10px] tabular text-ink-400">{p.pa ?? 0}pa · {p.hr ?? 0}hr</div>
                    </>
                  ) : (
                    <>
                      <div className="mono text-[12px] font-semibold tabular" style={{ color: themeColor }}>{(p.era_ip_weighted ?? 0).toFixed(2)}</div>
                      <div className="mono text-[10px] tabular text-ink-400">{p.ip ?? 0}ip · {p.k ?? 0}k</div>
                    </>
                  )}
                </div>
                <ChevronRight className="h-3 w-3 text-ink-500 group-hover:text-accent-400" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function GradeChip({ grade }: { grade: number }) {
  const tone = gradeTone(grade)
  const color = tone === 'pos' ? 'text-positive-500 border-positive-500/40 bg-positive-500/10' : tone === 'neg' ? 'text-negative-500 border-negative-500/40 bg-negative-500/10' : 'text-ink-200 border-ink-600 bg-ink-700'
  return (
    <span title={`Scout-grade proxy: ${gradeLabel(grade)}`} className={`mono inline-flex w-9 shrink-0 items-center justify-center rounded border px-1 py-0.5 text-[10px] font-bold tabular ${color}`}>
      {grade}
    </span>
  )
}

function TopRow({ player, rank, kind, themeColor }: { player: FarmPlayer; rank: number; kind: 'hitter' | 'pitcher'; themeColor: string }) {
  return (
    <li>
      <Link to={`/player/${player.mlb_player_id}`} className="group flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-ink-800/60">
        <span className="mono w-5 text-right text-[10px] font-bold tabular text-ink-500">{rank}</span>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[12px] font-semibold text-ink-100 group-hover:text-accent-300">{player.name}</div>
          <div className="mono text-[10px] tabular text-ink-400">
            {player.position_abbr ?? '—'} · age {player.age} · <span className="text-accent-300">{player.level}</span>
          </div>
        </div>
        <div className="text-right">
          <div className="mono text-[12px] font-semibold tabular" style={{ color: themeColor }}>
            {kind === 'hitter' ? (player.ops_pa_weighted ?? 0).toFixed(3) : (player.era_ip_weighted ?? 0).toFixed(2)}
          </div>
          <div className="mono text-[10px] tabular text-ink-400">
            {kind === 'hitter' ? `${player.pa ?? 0}pa` : `${player.ip ?? 0}ip`}
          </div>
        </div>
      </Link>
    </li>
  )
}
