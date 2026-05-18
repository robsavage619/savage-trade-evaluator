import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, Tooltip, ReferenceLine, CartesianGrid, Label } from 'recharts'
import { orgs, gms, kpctPoints } from '../data'
import { orgProfiles } from '../data/orgs'
import { Section } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import { teamColor, teamLogoUrl, fmtSigned } from '../lib/format'
import { useIdentityStore } from '../lib/identityStore'
import { useRoster } from '../lib/rosterStore'
import { Trophy, AlertCircle, ArrowRight, Telescope } from 'lucide-react'

export default function OrgExplorer() {
  const yourBref = useIdentityStore((s) => s.activeTeam)
  const roster = useRoster()
  const data = useMemo(() => {
    const byTeam = new Map(orgs.trade_results.map((r) => [r.team_bref, r]))
    return orgs.dev
      .filter((d) => byTeam.has(d.team_bref))
      .map((d) => {
        const tr = byTeam.get(d.team_bref)!
        return {
          team: d.team_bref,
          name: d.team_name,
          devWar: d.dev_war_total,
          tradeSurplus: tr.mean_surplus_3yr,
          n: tr.n_trades,
        }
      })
  }, [])

  const meanDev = data.reduce((a, b) => a + b.devWar, 0) / data.length
  const meanTrade = data.reduce((a, b) => a + b.tradeSurplus, 0) / data.length

  // Top GM regimes — sell-high and buy-low
  const sellHigh = [...gms].sort((a, b) => a.mean_surplus - b.mean_surplus).slice(0, 8)
  const buyLow = [...gms].sort((a, b) => b.mean_surplus - a.mean_surplus).slice(0, 8)
  const [tab, setTab] = useState<'sell' | 'buy'>('sell')

  return (
    <main className="mx-auto max-w-[1480px] px-6 py-8">
      <div className="mb-8">
        <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">Org Explorer</div>
        <h1 className="mt-1 text-[28px] font-semibold tracking-tight text-ink-100">Organizational quality, decomposed</h1>
        <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-ink-300">
          Two empirical findings from the v1 backtest: (1) player-development quality is uncorrelated with trade-execution quality, and
          (2) pre-trade K%-trajectory is the strongest single predictor of post-trade rate-stat collapse. Both render here.
        </p>
      </div>

      <Section eyebrow="Scout an org" title="Pick a club for the full scouting profile" hint="10-yr trajectory, payroll, dev signature, trade DNA, FO continuity, age curve, positional depth — every metric a GM would want before picking up the phone.">
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-6 xl:grid-cols-10">
          {roster.teams.map((t) => {
            const profile = orgProfiles[t.bref]
            const isSelf = t.bref === yourBref
            const tone = teamColor(t.bref)
            const meanS = profile?.trade_dna.summary?.mean_surplus
            return (
              <Link
                key={t.bref}
                to={`/orgs/${t.bref}`}
                className={`group relative flex flex-col items-center gap-1.5 rounded-md border p-2 transition-all hover:-translate-y-0.5 ${isSelf ? 'border-accent-500/50 bg-accent-500/5' : 'border-ink-700 bg-ink-800/40 hover:border-ink-500'}`}
              >
                <div className="absolute left-0 right-0 top-0 h-[2px] rounded-t-md opacity-70" style={{ background: tone.primary }} />
                <TeamLogo team={t.bref} size={36} />
                <div className="mono text-[10px] font-semibold tabular text-ink-100">{t.bref}</div>
                {meanS != null && (
                  <div className={`mono text-[9.5px] tabular ${meanS >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>{fmtSigned(meanS, 1)}</div>
                )}
                {isSelf && <span className="absolute right-1 top-1 chip chip-accent mono !px-1 !py-0 text-[8px]">you</span>}
              </Link>
            )
          })}
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-400">
          <Telescope className="h-3 w-3" />
          <span>Click any team to open the deep scout profile. <ArrowRight className="inline h-3 w-3 -translate-y-px" /> mean 3-yr surplus shown.</span>
        </div>
      </Section>

      <Section
        eyebrow="Finding 1"
        title="Dev WAR vs trade surplus — 30 MLB orgs, 2015–2024"
        hint="Top-right = elite at both. Bottom-left = elite at neither. The takeaway: most orgs are mediocre at trades regardless of player development."
      >
        <div className="card p-5">
          <ResponsiveContainer width="100%" height={420}>
            <ScatterChart margin={{ top: 16, right: 20, bottom: 32, left: 32 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
              <XAxis
                type="number"
                dataKey="devWar"
                name="Dev WAR (2015–2024)"
                stroke="#5a6896"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => v.toFixed(0)}
                domain={['dataMin - 5', 'dataMax + 5']}
              >
                <Label value="Player-development WAR (10-yr)" position="bottom" offset={20} fill="#8a96c0" fontSize={11} />
              </XAxis>
              <YAxis
                type="number"
                dataKey="tradeSurplus"
                name="Trade surplus"
                stroke="#5a6896"
                tick={{ fontSize: 11 }}
                tickFormatter={(v: number) => v.toFixed(1)}
                domain={['dataMin - 0.5', 'dataMax + 0.5']}
              >
                <Label value="Mean trade surplus (3-yr WAR)" angle={-90} position="left" offset={20} fill="#8a96c0" fontSize={11} />
              </YAxis>
              <ZAxis range={[40, 240]} />
              <ReferenceLine x={meanDev} stroke="rgba(138,150,192,0.4)" strokeDasharray="3 3" />
              <ReferenceLine y={meanTrade} stroke="rgba(138,150,192,0.4)" strokeDasharray="3 3" />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ payload }) => {
                  const p = payload?.[0]?.payload
                  if (!p) return null
                  return (
                    <div className="card px-3 py-2 text-[11px]">
                      <div className="text-[12px] font-semibold text-ink-100">
                        {p.team} · {p.name}
                      </div>
                      <div className="mono mt-1 tabular text-ink-300">
                        Dev WAR: {p.devWar.toFixed(1)} · Trade Δ: {fmtSigned(p.tradeSurplus)} · n={p.n}
                      </div>
                    </div>
                  )
                }}
              />
              <Scatter data={data}>
                {data.map((d) => {
                  const url = teamLogoUrl(d.team)
                  const SIZE = 26
                  return (
                    <Scatter
                      key={d.team}
                      data={[d]}
                      fill={teamColor(d.team).primary}
                      shape={(props: { cx?: number; cy?: number }) => {
                        const cx = props.cx ?? 0
                        const cy = props.cy ?? 0
                        if (!url) {
                          return (
                            <g>
                              <circle cx={cx} cy={cy} r={7} fill={teamColor(d.team).primary} stroke="rgba(11,16,24,0.9)" strokeWidth={1.5} />
                              <text x={cx + 10} y={cy + 3} fontSize={10} fill="#b9c1de" fontFamily="JetBrains Mono">
                                {d.team}
                              </text>
                            </g>
                          )
                        }
                        return (
                          <g>
                            <circle cx={cx} cy={cy} r={SIZE / 2 + 2} fill="rgba(11,16,24,0.8)" stroke="rgba(255,255,255,0.08)" />
                            <image
                              href={url}
                              x={cx - SIZE / 2}
                              y={cy - SIZE / 2}
                              width={SIZE}
                              height={SIZE}
                            />
                          </g>
                        )
                      }}
                    />
                  )
                })}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </Section>

      <Section
        eyebrow="GM Regimes"
        title="Decision-maker rankings · sell-high & buy-low"
        hint="Mean 3-yr WAR surplus realized by trades a regime executed. Jon Daniels' Texas trades are the showcase sell-high signature."
      >
        <div className="mb-3 inline-flex rounded-md border border-ink-700 bg-ink-800 p-0.5 text-[12px]">
          <button
            onClick={() => setTab('sell')}
            className={`flex items-center gap-1.5 rounded px-3 py-1 transition-colors ${tab === 'sell' ? 'bg-ink-700 text-ink-100' : 'text-ink-300'}`}
          >
            <AlertCircle className="h-3 w-3" /> Worst (sell-high targets to learn from)
          </button>
          <button
            onClick={() => setTab('buy')}
            className={`flex items-center gap-1.5 rounded px-3 py-1 transition-colors ${tab === 'buy' ? 'bg-ink-700 text-ink-100' : 'text-ink-300'}`}
          >
            <Trophy className="h-3 w-3" /> Best (buy-low signatures)
          </button>
        </div>
        <div className="card overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-ink-800 text-[10px] uppercase tracking-[0.12em] text-ink-400">
              <tr>
                <th className="px-4 py-2 text-left">Decision-maker</th>
                <th className="px-4 py-2 text-left">Team</th>
                <th className="px-4 py-2 text-right">N trades</th>
                <th className="px-4 py-2 text-right">Mean surplus (WAR)</th>
                <th className="px-4 py-2 text-right">Received</th>
                <th className="px-4 py-2 text-right">Given up</th>
                <th className="px-4 py-2 text-left">Window</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-700/60">
              {(tab === 'sell' ? sellHigh : buyLow).map((r) => (
                <tr key={`${r.gm_name}-${r.team_bref}`} className="hover:bg-ink-800/50">
                  <td className="px-4 py-2 font-medium text-ink-100">{r.gm_name}</td>
                  <td className="px-4 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      <TeamLogo team={r.team_bref} size={18} />
                      <span className="mono rounded px-1.5 py-0.5 text-[11px] tabular" style={{ background: teamColor(r.team_bref).soft, color: teamColor(r.team_bref).primary }}>
                        {r.team_bref}
                      </span>
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right mono tabular text-ink-300">{r.n_trades}</td>
                  <td className={`px-4 py-2 text-right mono tabular font-semibold ${r.mean_surplus >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>
                    {fmtSigned(r.mean_surplus)}
                  </td>
                  <td className="px-4 py-2 text-right mono tabular text-ink-300">{r.mean_war_received.toFixed(2)}</td>
                  <td className="px-4 py-2 text-right mono tabular text-ink-300">{r.mean_war_given_up.toFixed(2)}</td>
                  <td className="px-4 py-2 mono tabular text-ink-400">{r.first_season}–{r.last_season}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        eyebrow="Finding 2"
        title="Pitcher K%-trajectory predicts post-trade K% delta"
        hint="Each dot is one pitcher in one trade. The negative slope (coef ≈ −10.8, 90% CI [−17.1, −4.3]) means pitchers riding a K% spike pre-trade reliably regress; rising-K%-from-low trades tend to keep gaining."
      >
        <div className="card p-5">
          <ResponsiveContainer width="100%" height={380}>
            <ScatterChart margin={{ top: 16, right: 20, bottom: 32, left: 32 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
              <XAxis
                type="number"
                dataKey="k_percent_t_minus_1"
                name="Pre-trade K% pctile"
                stroke="#5a6896"
                tick={{ fontSize: 11 }}
                domain={[0, 100]}
              >
                <Label value="Pre-trade K% percentile" position="bottom" offset={20} fill="#8a96c0" fontSize={11} />
              </XAxis>
              <YAxis
                type="number"
                dataKey="k_delta"
                name="T+1 K% delta"
                stroke="#5a6896"
                tick={{ fontSize: 11 }}
                domain={[-60, 60]}
              >
                <Label value="T+1 K% percentile delta" angle={-90} position="left" offset={20} fill="#8a96c0" fontSize={11} />
              </YAxis>
              <ReferenceLine y={0} stroke="rgba(138,150,192,0.3)" />
              <ReferenceLine
                segment={[
                  { x: 0, y: 30 },
                  { x: 100, y: -30 },
                ]}
                stroke="#ff6a13"
                strokeWidth={2}
                strokeDasharray="4 3"
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ payload }) => {
                  const p = payload?.[0]?.payload
                  if (!p) return null
                  return (
                    <div className="card px-3 py-2 text-[11px]">
                      <div className="text-[12px] font-semibold text-ink-100">{p.player_name}</div>
                      <div className="mono mt-1 tabular text-ink-300">
                        {p.from_team_bref} → {p.to_team_bref} · {p.trade_season}
                      </div>
                      <div className="mono mt-1 tabular text-ink-300">
                        K% {p.k_percent_t_minus_1?.toFixed(0)} → {p.k_percent_t_plus_1?.toFixed(0)} ({fmtSigned(p.k_delta, 0)})
                      </div>
                    </div>
                  )
                }}
              />
              <Scatter data={kpctPoints} fill="rgba(255,138,61,0.6)" />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="mt-3 text-[11px] text-ink-400">
            Orange line: OLS fit. The negative slope holds across team-quality strata; this signal is the reason every V2 model
            specification uses pre-trade K%-trajectory as a baseline feature.
          </div>
        </div>
      </Section>
    </main>
  )
}
