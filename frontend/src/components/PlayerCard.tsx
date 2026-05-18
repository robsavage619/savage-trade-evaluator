import type { TradeLeg, Person, CareerWar, WarWindow } from '../types'
import { ageOn, fmtSigned, teamColor } from '../lib/format'
import { Sparkline } from './Sparkline'
import { TeamLogo } from './TeamLogo'

type Props = {
  leg: TradeLeg
  person?: Person
  career: CareerWar[]
  war?: WarWindow
}

const POS_LABEL: Record<string, string> = {
  P: 'RHP',
  C: 'C',
  '1B': '1B',
  '2B': '2B',
  '3B': '3B',
  SS: 'SS',
  LF: 'LF',
  CF: 'CF',
  RF: 'RF',
  DH: 'DH',
  OF: 'OF',
  IF: 'IF',
}

export function PlayerCard({ leg, person, career, war }: Props) {
  const tone = teamColor(leg.to_team_bref)
  const age = ageOn(person?.birth_date ?? null, leg.date)
  const pos = person?.primary_position_code ?? person?.primary_position_name ?? '—'
  const playerCareer = career.filter((c) => c.mlb_player_id === leg.mlb_player_id)
  const years = playerCareer.map((c) => c.year)
  const startYr = Math.min(...years, leg.trade_season - 3)
  const endYr = Math.max(...years, leg.trade_season + 3)
  const sparkVals: Array<number | null> = []
  for (let y = startYr; y <= endYr; y++) {
    const rows = playerCareer.filter((c) => c.year === y)
    sparkVals.push(rows.length ? rows.reduce((a, b) => a + (b.war ?? 0), 0) : null)
  }
  const highlightIdx = leg.trade_season - startYr
  const labelPos = (POS_LABEL[pos] ?? pos).toString().slice(0, 4)

  return (
    <div className="card relative overflow-hidden p-3.5">
      <div
        className="absolute left-0 right-0 top-0 h-[2px]"
        style={{ background: tone.primary }}
        aria-hidden
      />
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-[0.14em] text-ink-400">
            <TeamLogo team={leg.from_team_bref} size={14} />
            {leg.from_team_bref} → {leg.to_team_bref}
            <TeamLogo team={leg.to_team_bref} size={14} />
          </div>
          <div className="mt-0.5 text-[15px] font-semibold tracking-tight text-ink-100">{leg.player_name}</div>
          <div className="mt-0.5 flex items-center gap-2 text-[11px] text-ink-300">
            <span className="mono">{labelPos}</span>
            {age != null ? <span>· {age}y</span> : null}
            {person?.height_inches ? (
              <span>
                · {Math.floor(person.height_inches / 12)}&apos;{person.height_inches % 12}″
              </span>
            ) : null}
            {person?.pitch_hand ? <span>· {person.pitch_hand}HP</span> : null}
            {person?.bat_side ? <span>· {person.bat_side}HB</span> : null}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">T+3 WAR</div>
          <div className="mono mt-0.5 text-[18px] font-semibold tabular text-ink-100">
            {war?.war_t_plus_3 != null ? fmtSigned(war.war_t_plus_3) : '—'}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <Sparkline values={sparkVals} width={160} height={36} highlightIndex={highlightIdx} accent={tone.primary} />
        <div className="grid grid-cols-3 gap-2 text-right">
          <div>
            <div className="text-[9px] uppercase tracking-wider text-ink-400">T-1</div>
            <div className="mono text-[12px] tabular text-ink-200">
              {war?.war_t_minus_1 != null ? fmtSigned(war.war_t_minus_1, 1) : '—'}
            </div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-ink-400">T+1</div>
            <div className="mono text-[12px] tabular text-ink-200">
              {war?.war_t_plus_1 != null ? fmtSigned(war.war_t_plus_1, 1) : '—'}
            </div>
          </div>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-ink-400">T+2</div>
            <div className="mono text-[12px] tabular text-ink-200">
              {war?.war_t_plus_2 != null ? fmtSigned(war.war_t_plus_2, 1) : '—'}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
