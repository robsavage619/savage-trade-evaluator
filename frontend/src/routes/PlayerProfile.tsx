import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ArrowLeft, AlertCircle, Terminal, Copy, ClipboardCheck, X, CheckCircle2, RotateCcw, Sparkles, Users, ChevronRight } from 'lucide-react'
import { ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ReferenceLine, CartesianGrid, ScatterChart, Scatter, ZAxis } from 'recharts'
import { loadPlayerProfile, type PlayerProfile, type PctilePitcherRow, type PctileBatterRow } from '../data/playerTypes'
import { findPlayer } from '../data/players'
import { LEVEL_LABELS } from '../data/farm'
import { useFarmPlayerLookup } from '../lib/farmStore'
import { scoutGrade, gradeTone, gradeLabel } from '../lib/prospectGrade'
import { TeamLogo } from '../components/TeamLogo'
import { Section } from '../components/Section'
import { PercentileRadar } from '../components/PercentileRadar'
import { fmtSigned, fmtMoney } from '../lib/format'
import { TEAM_THEME, useIdentityStore } from '../lib/identityStore'
import { findComps, type CompResult } from '../lib/comps'
import { composePlayerScoutPrompt } from '../lib/composePlayerScout'
import { useReasoningStore, parseReasoningResponse } from '../lib/reasoningStore'

const PLAYER_SCOUT_BASE = -3_000_000

const HEADSHOT = (id: number) => `https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_240,q_auto:best/v1/people/${id}/headshot/67/current`

export default function PlayerProfileRoute() {
  const params = useParams<{ id: string }>()
  const id = Number(params.id)
  const [profile, setProfile] = useState<PlayerProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const yourBref = useIdentityStore((s) => s.activeTeam)
  const liveLookup = findPlayer(id)
  const farmLookup = useFarmPlayerLookup()

  useEffect(() => {
    setLoading(true)
    loadPlayerProfile(id).then((p) => { setProfile(p); setLoading(false) })
  }, [id])

  // All hooks must run on every render — compute against profile-or-null and gate render below.
  const isPitcher = profile?.is_pitcher ?? false
  const latestPct = profile
    ? (isPitcher ? profile.percentiles.pitching[profile.percentiles.pitching.length - 1] : profile.percentiles.batting[profile.percentiles.batting.length - 1])
    : null
  const radarMetrics = useMemo(() => buildRadarMetrics(isPitcher, latestPct ?? null), [isPitcher, latestPct])
  const careerSeriesData = useMemo(() => profile ? buildCareerSeries(profile) : [], [profile])
  const salarySeriesData = useMemo(() => profile ? buildSalarySeries(profile) : [], [profile])
  const movementData = useMemo(() => profile ? buildMovementData(profile) : [], [profile])
  const arsenalUsageData = useMemo(() => profile ? buildArsenalUsageOverTime(profile) : { rows: [], pitchTypes: [] }, [profile])
  const comps = useMemo<CompResult[]>(() => profile ? findComps(profile.bio.mlb_player_id, { limit: 8 }) : [], [profile])

  // AI scouting drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [paste, setPaste] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)
  const [pasteOk, setPasteOk] = useState(false)
  const [copied, setCopied] = useState(false)
  const scoutId = PLAYER_SCOUT_BASE - id
  const override = useReasoningStore((s) => s.overrides[scoutId])
  const setReasoning = useReasoningStore((s) => s.set)
  const prompt = useMemo(
    () => profile ? composePlayerScoutPrompt({ profile, teamBref: liveLookup?.team.bref ?? null, yourBref, comps }) : '',
    [profile, liveLookup, yourBref, comps],
  )

  async function copyPrompt() {
    if (!prompt) return
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  function applyPaste() {
    setPasteError(null)
    setPasteOk(false)
    const r = parseReasoningResponse(paste)
    if ('error' in r) { setPasteError(r.error); return }
    setReasoning(scoutId, r, `Claude Code · player workup`)
    setPasteOk(true)
  }

  if (loading) return <main className="mx-auto max-w-[1480px] px-6 py-10 text-[14px] text-ink-400">Loading player profile…</main>
  if (!profile) {
    // Fall back to farm-only profile if we have MiLB data for this player
    const farmEntry = farmLookup.get(id)
    if (farmEntry) return <FarmOnlyProfile player={farmEntry.player} parentBref={farmEntry.parentBref} />
    return <main className="mx-auto max-w-[1480px] px-6 py-10 text-[14px] text-ink-400">Player profile not found. <Link to="/build" className="text-accent-400 underline">Back to builder</Link></main>
  }

  const bio = profile.bio
  const teamBref = liveLookup?.team.bref
  const theme = teamBref ? (TEAM_THEME[teamBref] ?? TEAM_THEME.NYM) : TEAM_THEME.NYM
  const accent = theme.primary
  const careerWar = (isPitcher ? profile.career.pitching : profile.career.batting).reduce((a, r) => a + (r.war ?? 0), 0)
  const lastSeason = lastWarSeason(profile)
  const lastSalary = lastSalaryFor(profile)
  const last3War = recentNYearWar(profile, 3)

  return (
    <main className="mx-auto max-w-[1640px] px-6 py-6">
      {/* Hero band */}
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="card relative mb-6 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-1 w-full" style={{ background: `linear-gradient(90deg, ${theme.primary}, ${theme.secondary})` }} />
        <div className="flex flex-wrap items-start justify-between gap-6 p-5">
          <div className="flex items-start gap-4">
            <Link to={teamBref ? `/orgs/${teamBref}` : '/build'} className="grid h-9 w-9 place-items-center rounded-md border border-ink-700 text-ink-400 transition-colors hover:border-ink-500 hover:text-ink-100">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div
              className="relative h-[88px] w-[88px] shrink-0 overflow-hidden rounded-md border border-ink-700 bg-ink-800"
              style={{ borderColor: `${accent}55` }}
            >
              <img src={HEADSHOT(id)} alt={bio.full_name} className="h-full w-full object-cover" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">Player Workup</div>
              <div className="flex items-center gap-2">
                <div className="text-[26px] font-semibold tracking-tight text-ink-100">{bio.full_name}</div>
                {liveLookup?.player.status_code && liveLookup.player.status_code !== 'A' && (
                  <span className="chip chip-neg mono"><AlertCircle className="h-2.5 w-2.5" /> {liveLookup.player.status_code}</span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-300">
                {teamBref && <span className="inline-flex items-center gap-1.5"><TeamLogo team={teamBref} size={16} /> {liveLookup?.team.name}</span>}
                {liveLookup?.player.jersey && <span>#{liveLookup.player.jersey}</span>}
                <span>{bio.primary_position_name ?? '—'}</span>
                {liveLookup?.player.age != null && <span>· age {liveLookup.player.age}</span>}
                {bio.height_inches && <span>· {Math.floor(bio.height_inches / 12)}&apos;{bio.height_inches % 12}&quot;</span>}
                {bio.weight_lbs && <span>· {bio.weight_lbs}lb</span>}
                {bio.bat_side && <span>· {bio.bat_side}HB</span>}
                {bio.pitch_hand && <span>· {bio.pitch_hand}HP</span>}
                {bio.birth_country && <span>· {bio.birth_country}</span>}
              </div>
              <div className="mt-1 text-[11px] text-ink-400">
                Debut {bio.mlb_debut_date ?? '—'} {bio.mlb_debut_date && <span className="text-ink-500">· {Math.max(0, (new Date()).getFullYear() - new Date(bio.mlb_debut_date).getFullYear())} yr service proxy</span>}
              </div>
              {profile.awards && profile.awards.length > 0 ? (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  {awardChips(profile.awards).map((c, i) => (
                    <span key={i} className={`chip mono ${c.tone}`} title={c.title}>{c.label}</span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip mono">{profile.trades.length} trade{profile.trades.length === 1 ? '' : 's'} on record</span>
            <span className="chip mono">{comps.length} comps found</span>
            <button
              onClick={() => setDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 transition-colors hover:bg-accent-400"
            >
              <Terminal className="h-3.5 w-3.5" /> Scout with Claude Code
            </button>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-ink-700 px-5 py-4 md:grid-cols-6">
          <HeroKpi label="Career WAR" value={fmtSigned(careerWar, 1)} sub={`${(isPitcher ? profile.career.pitching : profile.career.batting).length} seasons`} tone={careerWar >= 20 ? 'pos' : careerWar < 0 ? 'neg' : 'neutral'} />
          <HeroKpi label="3-yr WAR" value={fmtSigned(last3War, 1)} sub="trailing 3 seasons" tone={last3War >= 0 ? 'pos' : 'neg'} />
          <HeroKpi label={`Last (${lastSeason ?? '—'})`} value={fmtSigned(lastWar(profile) ?? 0, 1)} sub="WAR" tone={(lastWar(profile) ?? 0) >= 0 ? 'pos' : 'neg'} />
          <HeroKpi label="Last salary" value={lastSalary != null ? fmtMoney(lastSalary) : '—'} sub={lastSeason ? `${lastSeason} payroll` : ''} />
          <HeroKpi label="$/WAR (last)" value={dollarPerWar(profile)} sub="paid vs earned" />
          <HeroKpi label={isPitcher ? 'xERA' : 'xwOBA'} value={latestPctLabel(isPitcher, latestPct)} sub="MLB pctile rank · most recent" tone={latestPctTone(isPitcher, latestPct)} />
        </div>
      </motion.div>

      {/* Claude scout analysis (if applied) */}
      {override?.reasoning ? (
        <div className="card mb-6 p-5">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Claude scout workup</div>
              <div className="text-[15px] font-semibold leading-snug text-ink-100">{override.reasoning.headline}</div>
            </div>
            <span className="chip chip-pos mono">applied {new Date(override.savedAt).toLocaleString()}</span>
          </div>
          <div className="mt-3 grid gap-4 md:grid-cols-[1fr_280px]">
            <div className="space-y-3 text-[13px] leading-relaxed text-ink-200">
              <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Thesis</div><p className="mt-1">{override.reasoning.thesis}</p></div>
              <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Key drivers</div>
                <ul className="mt-1 space-y-2">{override.reasoning.keyDrivers.map((d, i) => (
                  <li key={i} className="rounded-md border border-ink-700 bg-ink-800/40 p-2.5">
                    <div className="flex items-center gap-2">{d.chip && <span className="chip chip-accent mono">{d.chip}</span>}<span className="text-[12.5px] font-semibold text-ink-100">{d.title}</span></div>
                    <div className="mt-1 text-[12px] text-ink-300">{d.body}</div>
                  </li>
                ))}</ul>
              </div>
              <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Recommendation</div><p className="mt-1 font-semibold text-ink-100">{override.reasoning.recommendation}</p></div>
            </div>
            <div className="space-y-3 border-l border-ink-700 pl-4">
              <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Watch-outs</div>
                <ul className="mt-1 space-y-2 text-[11px]">{override.reasoning.watchOuts.map((w, i) => (
                  <li key={i} className="rounded-md bg-negative-500/[0.06] p-2"><div className="font-semibold text-ink-100">{w.title}</div><div className="mt-0.5 text-ink-300">{w.body}</div></li>
                ))}</ul>
              </div>
              <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Grounding</div>
                <ul className="mt-1 space-y-2 text-[11px]">{override.reasoning.citations.map((c, i) => (
                  <li key={i} className="rounded-md border border-ink-700 bg-ink-800/60 p-2"><div className="mono font-semibold text-accent-300">[{i + 1}] {c.label}</div><div className="mt-0.5 text-ink-300">{c.detail}</div></li>
                ))}</ul>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Body */}
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        {/* Career WAR + salary chart */}
        <Section eyebrow="Career WAR" title="Production trajectory · age x-axis" hint="Bar = WAR per season. Salary line shows pay vs production.">
          <div className="card p-4">
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={careerSeriesData} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                <XAxis dataKey="year" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="war" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis yAxisId="salary" orientation="right" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
                <Tooltip contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }} formatter={(v) => typeof v === 'number' ? (v >= 100_000 ? `$${(v / 1e6).toFixed(1)}M` : v.toFixed(1)) : String(v)} />
                <ReferenceLine yAxisId="war" y={0} stroke="rgba(138,150,192,0.3)" />
                <Bar yAxisId="war" dataKey="war" fill={accent} radius={[3, 3, 0, 0]} name="WAR" />
                <Line yAxisId="salary" type="monotone" dataKey="salary" stroke="#3ddc97" strokeWidth={2} dot={{ r: 2 }} name="salary" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Section>

        {/* Statcast radar */}
        <Section eyebrow="Statcast Fingerprint" title={`${isPitcher ? 'Pitcher' : 'Hitter'} percentile ranks · most recent season`} hint="Green = elite, red = below-average. 67th+ = top third, 34th- = bottom third.">
          <div className="card flex items-center justify-center p-4">
            {radarMetrics.length === 0 ? (
              <div className="py-8 text-[12px] text-ink-400">No Statcast coverage for this player yet.</div>
            ) : (
              <PercentileRadar metrics={radarMetrics} size={340} accent={accent} />
            )}
          </div>
        </Section>

        {/* Arsenal (pitchers) or rate-stat history (hitters) */}
        {isPitcher && profile.arsenal.length > 0 ? (
          <Section eyebrow="Arsenal" title="Pitch usage over time" hint="Usage % per pitch type — stacked. Watch for mix shifts (the Pressly signature).">
            <div className="card p-4">
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={arsenalUsageData.rows} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                  <XAxis dataKey="year" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} unit="%" domain={[0, 100]} />
                  <Tooltip contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }} />
                  {arsenalUsageData.pitchTypes.map((pt, i) => (
                    <Bar key={pt} dataKey={pt} stackId="a" fill={PITCH_COLORS[i % PITCH_COLORS.length]} name={pt} />
                  ))}
                </ComposedChart>
              </ResponsiveContainer>
              <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-ink-400">
                {arsenalUsageData.pitchTypes.map((pt, i) => (
                  <span key={pt} className="inline-flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: PITCH_COLORS[i % PITCH_COLORS.length] }} />
                    {pt}
                  </span>
                ))}
              </div>
            </div>
          </Section>
        ) : null}

        {/* Pitch movement scatter (pitchers) */}
        {isPitcher && movementData.length > 0 ? (
          <Section eyebrow="Pitch Movement" title="Break profile · latest season" hint="X = horizontal break, Y = induced vertical break (inches). Larger dot = more usage.">
            <div className="card p-4">
              <ResponsiveContainer width="100%" height={260}>
                <ScatterChart margin={{ top: 8, right: 12, bottom: 24, left: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                  <XAxis type="number" dataKey="horizontal" stroke="#5a6896" tick={{ fontSize: 11 }} name="Horizontal break (in)" domain={[-20, 20]} />
                  <YAxis type="number" dataKey="vertical" stroke="#5a6896" tick={{ fontSize: 11 }} name="Induced vertical (in)" domain={[-30, 30]} />
                  <ZAxis dataKey="usage" range={[40, 280]} />
                  <ReferenceLine x={0} stroke="rgba(138,150,192,0.3)" />
                  <ReferenceLine y={0} stroke="rgba(138,150,192,0.3)" />
                  <Tooltip content={({ payload }) => {
                    const p = payload?.[0]?.payload
                    if (!p) return null
                    return <div className="card px-3 py-2 text-[11px]"><div className="font-semibold text-ink-100">{p.pitch_name || p.pitch_type}</div><div className="mono mt-1 tabular text-ink-300">{p.avg_speed?.toFixed(1)} mph · usage {p.usage?.toFixed(0)}%</div></div>
                  }} />
                  <Scatter data={movementData} fill={accent} fillOpacity={0.7} stroke={accent} />
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          </Section>
        ) : null}

        {/* Trade history */}
        <Section eyebrow="Trade History" title="Every time this player moved" hint="Each card links to the full workspace if the trade is in the V1 backtest.">
          <div className="card overflow-hidden">
            {profile.trades.length === 0 ? (
              <div className="grid place-items-center p-8 text-[12px] text-ink-400">Never been traded.</div>
            ) : (
              <ul className="divide-y divide-ink-700/60">
                {profile.trades.map((t) => (
                  <li key={t.trade_event_id}>
                    <Link to={`/trade/${t.trade_event_id}`} className="flex items-center justify-between px-3 py-2 hover:bg-ink-800/50">
                      <div className="flex items-center gap-2">
                        <TeamLogo team={t.from_team_bref} size={18} />
                        <span className="text-[11px] text-ink-400">→</span>
                        <TeamLogo team={t.to_team_bref} size={18} />
                        <span className="ml-2 text-[12px] font-medium text-ink-100">{t.from_team_bref} → {t.to_team_bref}</span>
                      </div>
                      <span className="mono text-[11px] tabular text-ink-400">{t.trade_date}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>

        {/* Statcast trends */}
        <Section eyebrow="Rate-stat trends" title={`${isPitcher ? 'K% · Whiff% · Chase%' : 'xwOBA · Exit velo · Hard-hit%'} over time`} hint="Multi-year percentile-rank trajectory.">
          <div className="card p-4">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={(isPitcher ? profile.percentiles.pitching : profile.percentiles.batting) as Array<Record<string, unknown>>} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                <XAxis dataKey="year" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} domain={[0, 100]} unit=" pctile" />
                <ReferenceLine y={50} stroke="rgba(138,150,192,0.3)" strokeDasharray="3 3" />
                <Tooltip contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }} />
                {isPitcher ? (
                  <>
                    <Line type="monotone" dataKey="k_percent" stroke="#3ddc97" strokeWidth={2} name="K%" dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="whiff_percent" stroke="#ff8a3d" strokeWidth={2} name="Whiff%" dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="chase_percent" stroke="#6699ff" strokeWidth={2} name="Chase%" dot={{ r: 3 }} />
                  </>
                ) : (
                  <>
                    <Line type="monotone" dataKey="xwoba" stroke="#3ddc97" strokeWidth={2} name="xwOBA" dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="exit_velocity" stroke="#ff8a3d" strokeWidth={2} name="Exit velo" dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="hard_hit_percent" stroke="#6699ff" strokeWidth={2} name="Hard hit%" dot={{ r: 3 }} />
                  </>
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Section>

        {/* Salary efficiency */}
        <Section eyebrow="Pay vs Production" title="Salary curve overlaid on WAR-earned-value" hint="When the lines diverge, surplus or overpay is on the table.">
          <div className="card p-4">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={salarySeriesData} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                <XAxis dataKey="year" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${(v / 1e6).toFixed(0)}M`} />
                <Tooltip contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }} formatter={(v) => typeof v === 'number' ? `$${(v / 1e6).toFixed(1)}M` : String(v)} />
                <Line type="monotone" dataKey="salary" stroke="#3ddc97" strokeWidth={2} name="paid" dot={{ r: 3 }} />
                <Line type="monotone" dataKey="warValue" stroke={accent} strokeWidth={2} name="WAR earned ($8M/WAR)" strokeDasharray="3 3" dot={{ r: 2 }} />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="mt-2 text-[11px] text-ink-400">
              Dashed line uses the FanGraphs-style $8M/WAR coefficient — the naive baseline this product is built to beat.
            </div>
          </div>
        </Section>
      </div>

      {/* Comparables */}
      <div className="mt-6">
        <Section eyebrow="League Comparables" title="Similar profiles · age, position, Statcast fingerprint" hint="Closest matches by Euclidean distance over the same rate-stat percentile vector + age band.">
          {comps.length === 0 ? (
            <div className="card p-6 text-[12px] text-ink-400">No comparable players found.</div>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {comps.map((c) => (
                <Link key={c.player.id} to={`/player/${c.player.id}`} className="group card relative overflow-hidden p-3 transition-all hover:-translate-y-0.5 hover:border-accent-500/40">
                  <div className="absolute right-2 top-2 mono text-[10px] tabular text-ink-400">{c.score.toFixed(0)}<span className="text-ink-500">/100</span></div>
                  <div className="flex items-center gap-2.5">
                    <TeamLogo team={c.player.team} size={26} />
                    <div className="min-w-0">
                      <div className="truncate text-[13px] font-semibold text-ink-100 group-hover:text-accent-300">{c.player.name}</div>
                      <div className="mono text-[10px] tabular text-ink-400">
                        {c.player.team} · age {c.player.age ?? '?'}
                        {c.player.war != null ? ` · ${c.player.war >= 0 ? '+' : ''}${c.player.war.toFixed(1)} WAR` : ''}
                        {c.player.salary != null ? ` · ${fmtMoney(c.player.salary)}` : ''}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-[10px] text-ink-400">
                    <span className="inline-flex items-center gap-1"><Users className="h-2.5 w-2.5" /> Δage {c.ageDelta}</span>
                    <span className="inline-flex items-center gap-1">ΔWAR {c.warDelta.toFixed(1)}</span>
                    <ChevronRight className="ml-auto h-3 w-3 text-ink-500 group-hover:text-accent-400" />
                  </div>
                  <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-ink-800">
                    <div className="h-full bg-accent-500/70" style={{ width: `${c.score}%` }} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Section>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-400">
        <span className="mono">Player profile · bWAR + Statcast · {bio.mlb_player_id} · {profile.percentiles.pitching.length + profile.percentiles.batting.length} Statcast seasons</span>
        <span className="mono">{teamBref ? `Scouted from ${yourBref}'s perspective` : 'Free-agent / unrostered'}</span>
      </div>

      {/* Scout drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} onClick={() => setDrawerOpen(false)} />
            <motion.aside initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', stiffness: 300, damping: 32 }} className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-ink-700 bg-ink-900">
              <header className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400"><Terminal className="h-4 w-4" /></div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Scout workup with Claude Code</div>
                    <div className="text-[14px] font-semibold text-ink-100">{bio.full_name}</div>
                  </div>
                </div>
                <button onClick={() => setDrawerOpen(false)} className="rounded-md p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100"><X className="h-4 w-4" /></button>
              </header>
              <div className="flex-1 overflow-y-auto p-5">
                <section className="mb-5">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 1 · Generated prompt</div>
                      <div className="text-[12px] text-ink-300">Bio · 5-yr WAR + salary · Statcast fingerprint · arsenal · trades · 5 league comps.</div>
                    </div>
                    <button onClick={copyPrompt} className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 hover:bg-accent-400">
                      {copied ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {copied ? 'Copied' : 'Copy prompt'}
                    </button>
                  </div>
                  <pre className="max-h-64 overflow-y-auto rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[11px] leading-relaxed text-ink-300 mono whitespace-pre-wrap">{prompt}</pre>
                </section>
                <section className="mb-5 rounded-md border border-ink-700 bg-ink-800/50 p-4">
                  <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400"><Sparkles className="h-3 w-3" /> Step 2 · In Claude Code</div>
                  <ol className="ml-4 list-decimal space-y-1 text-[12px] text-ink-200 marker:text-ink-500">
                    <li>Paste the prompt into Claude Code chat</li>
                    <li>Claude returns a single fenced <code className="mono rounded bg-ink-700 px-1 text-[10.5px]">```json</code> block</li>
                    <li>Copy that block (fences OK) and paste below</li>
                  </ol>
                </section>
                <section>
                  <div className="mb-2 flex items-center justify-between">
                    <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 3 · Paste response</div></div>
                    {override && (
                      <button onClick={() => { useReasoningStore.getState().clear(scoutId); setPaste(''); setPasteError(null); setPasteOk(false) }} className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1 text-[11px] text-ink-300 hover:border-negative-500/50 hover:text-negative-500">
                        <RotateCcw className="h-3 w-3" /> Clear saved
                      </button>
                    )}
                  </div>
                  <textarea value={paste} onChange={(e) => setPaste(e.target.value)} placeholder="```json&#10;{ ... }&#10;```" rows={10} className="mono w-full rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[12px] leading-relaxed text-ink-200 placeholder:text-ink-500 focus:border-accent-500/50 focus:outline-none" spellCheck={false} />
                  {pasteError && <div className="mt-2 flex items-start gap-2 rounded-md border border-negative-500/40 bg-negative-500/10 px-3 py-2 text-[12px] text-negative-500"><AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{pasteError}</span></div>}
                  {pasteOk && <div className="mt-2 flex items-center gap-2 rounded-md border border-positive-500/40 bg-positive-500/10 px-3 py-2 text-[12px] text-positive-500"><CheckCircle2 className="h-3.5 w-3.5" /> Workup applied — see the analysis card at the top.</div>}
                  <div className="mt-3 flex items-center justify-end gap-2">
                    <button onClick={() => setDrawerOpen(false)} className="rounded-md border border-ink-700 px-3 py-1.5 text-[12px] text-ink-300 hover:border-ink-500 hover:text-ink-100">Done</button>
                    <button onClick={applyPaste} disabled={!paste.trim()} className="rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-500">Parse &amp; apply</button>
                  </div>
                </section>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </main>
  )
}

function awardChips(awards: import('../data/playerTypes').AwardRow[]) {
  const counts: Record<string, number> = {}
  for (const a of awards) {
    const k = (a.award_name || '').toLowerCase()
    let bucket: string | null = null
    if (k.includes('all-star') || k.includes('all star')) bucket = 'All-Star'
    else if (k.includes('mvp')) bucket = 'MVP'
    else if (k.includes('cy young')) bucket = 'Cy Young'
    else if (k.includes('silver slugger')) bucket = 'Silver Slugger'
    else if (k.includes('gold glove')) bucket = 'Gold Glove'
    else if (k.includes('rookie of the year')) bucket = 'ROY'
    if (bucket) counts[bucket] = (counts[bucket] ?? 0) + 1
  }
  const TONE: Record<string, string> = {
    'MVP': 'chip-accent',
    'Cy Young': 'chip-accent',
    'All-Star': '',
    'Silver Slugger': '',
    'Gold Glove': '',
    'ROY': 'chip-pos',
  }
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([label, n]) => ({
    label: n > 1 ? `${n}× ${label}` : label,
    tone: TONE[label] ?? '',
    title: `${n}× ${label}`,
  }))
}

function HeroKpi({ label, value, sub, tone = 'neutral' }: { label: string; value: string; sub?: string; tone?: 'pos' | 'neg' | 'neutral' }) {
  const cls = tone === 'pos' ? 'text-positive-500' : tone === 'neg' ? 'text-negative-500' : 'text-ink-100'
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-400">{label}</div>
      <div className={`mono mt-0.5 text-[18px] font-semibold tabular leading-none ${cls}`}>{value}</div>
      {sub && <div className="mt-1 text-[10.5px] text-ink-400">{sub}</div>}
    </div>
  )
}

const PITCH_COLORS = ['#ff6a13', '#3ddc97', '#6699ff', '#ff5d73', '#ffb37a', '#b9c1de', '#a060ff']

function buildRadarMetrics(isPitcher: boolean, p: PctilePitcherRow | PctileBatterRow | null) {
  if (!p) return []
  if (isPitcher) {
    const pp = p as PctilePitcherRow
    return [
      { label: 'K%', value: pp.k_percent },
      { label: 'Whiff%', value: pp.whiff_percent },
      { label: 'Chase%', value: pp.chase_percent },
      { label: 'BB%', value: pp.bb_percent },
      { label: 'xwOBA', value: pp.xwoba },
      { label: 'FB velo', value: pp.fb_velocity },
      { label: 'FB spin', value: pp.fb_spin },
      { label: 'Curve spin', value: pp.curve_spin },
      { label: 'Hard hit%', value: pp.hard_hit_percent },
      { label: 'Barrel%', value: pp.brl_percent },
    ]
  }
  const bp = p as PctileBatterRow
  return [
    { label: 'xwOBA', value: bp.xwoba },
    { label: 'xBA', value: bp.xba },
    { label: 'xSLG', value: bp.xslg },
    { label: 'Exit velo', value: bp.exit_velocity },
    { label: 'Hard hit%', value: bp.hard_hit_percent },
    { label: 'Barrel%', value: bp.brl_percent },
    { label: 'Chase%', value: bp.chase_percent },
    { label: 'Whiff%', value: bp.whiff_percent },
    { label: 'Bat speed', value: bp.bat_speed },
    { label: 'Sprint', value: bp.sprint_speed },
  ]
}

function buildCareerSeries(profile: PlayerProfile) {
  const rows = profile.is_pitcher ? profile.career.pitching : profile.career.batting
  // Aggregate by year (combine stints)
  const byYear = new Map<number, { year: number; war: number; salary: number | null }>()
  for (const r of rows) {
    const y = byYear.get(r.year) ?? { year: r.year, war: 0, salary: null }
    y.war += r.war ?? 0
    if (r.salary != null) y.salary = Math.max(y.salary ?? 0, r.salary)
    byYear.set(r.year, y)
  }
  return [...byYear.values()].sort((a, b) => a.year - b.year)
}

function buildSalarySeries(profile: PlayerProfile) {
  const career = buildCareerSeries(profile)
  return career.map((r) => ({
    year: r.year,
    salary: r.salary,
    warValue: r.war > 0 ? r.war * 8_000_000 : 0,
  }))
}

function buildMovementData(profile: PlayerProfile) {
  if (!profile.pitch_movement.length) return []
  const latestYear = Math.max(...profile.pitch_movement.map((m) => m.year))
  return profile.pitch_movement
    .filter((m) => m.year === latestYear)
    .map((m) => ({
      pitch_type: m.pitch_type,
      pitch_name: m.pitch_name,
      horizontal: m.horizontal_break_inches,
      vertical: m.induced_vertical ?? m.vertical_break_inches,
      usage: (m.pitch_usage_pct ?? 0),
      avg_speed: m.avg_speed,
    }))
}

function buildArsenalUsageOverTime(profile: PlayerProfile) {
  if (!profile.arsenal.length) return { rows: [], pitchTypes: [] }
  const pitchTypeSet = new Set(profile.arsenal.map((a) => a.pitch_type))
  const pitchTypes = [...pitchTypeSet].sort()
  const byYear = new Map<number, Record<string, number>>()
  for (const a of profile.arsenal) {
    const y = byYear.get(a.year) ?? {}
    y[a.pitch_type] = a.pitch_usage ?? 0
    byYear.set(a.year, y)
  }
  const rows = [...byYear.entries()].sort(([a], [b]) => a - b).map(([year, vals]) => ({ year, ...vals }))
  return { rows, pitchTypes }
}

function lastWarSeason(p: PlayerProfile): number | null {
  const rows = p.is_pitcher ? p.career.pitching : p.career.batting
  return rows.length ? Math.max(...rows.map((r) => r.year)) : null
}
function lastWar(p: PlayerProfile): number | null {
  const y = lastWarSeason(p)
  if (!y) return null
  const rows = (p.is_pitcher ? p.career.pitching : p.career.batting).filter((r) => r.year === y)
  return rows.reduce((a, r) => a + (r.war ?? 0), 0)
}
function lastSalaryFor(p: PlayerProfile): number | null {
  const y = lastWarSeason(p)
  if (!y) return null
  const rows = (p.is_pitcher ? p.career.pitching : p.career.batting).filter((r) => r.year === y)
  const sal = rows.map((r) => r.salary).filter((s): s is number => s != null)
  return sal.length ? Math.max(...sal) : null
}
function recentNYearWar(p: PlayerProfile, n: number): number {
  const y = lastWarSeason(p)
  if (!y) return 0
  return (p.is_pitcher ? p.career.pitching : p.career.batting)
    .filter((r) => r.year >= y - (n - 1) && r.year <= y)
    .reduce((a, r) => a + (r.war ?? 0), 0)
}
function dollarPerWar(p: PlayerProfile): string {
  const sal = lastSalaryFor(p)
  const war = lastWar(p)
  if (sal == null || war == null || war <= 0) return '—'
  return `$${(sal / war / 1e6).toFixed(1)}M`
}
function latestPctLabel(isPitcher: boolean, p: PctilePitcherRow | PctileBatterRow | null): string {
  if (!p) return '—'
  if (isPitcher) {
    const v = (p as PctilePitcherRow).xera
    return v != null ? `${v.toFixed(0)} pct` : '—'
  }
  const v = (p as PctileBatterRow).xwoba
  return v != null ? `${v.toFixed(0)} pct` : '—'
}
function latestPctTone(isPitcher: boolean, p: PctilePitcherRow | PctileBatterRow | null): 'pos' | 'neg' | 'neutral' {
  if (!p) return 'neutral'
  const v = isPitcher ? (p as PctilePitcherRow).xera : (p as PctileBatterRow).xwoba
  if (v == null) return 'neutral'
  if (v >= 67) return 'pos'
  if (v < 34) return 'neg'
  return 'neutral'
}

// ────────────────────────────────────────────── Farm-only profile (no MLB JSON)
function FarmOnlyProfile({ player, parentBref }: { player: import('../data/farm').FarmPlayer; parentBref: string }) {
  const theme = TEAM_THEME[parentBref] ?? TEAM_THEME.NYM
  const accent = theme.primary
  const grade = scoutGrade(player)
  const tone = gradeTone(grade)
  const isPitcher = player.is_pitcher

  return (
    <main className="mx-auto max-w-[1640px] px-6 py-6">
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="card relative mb-6 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-1 w-full" style={{ background: `linear-gradient(90deg, ${theme.primary}, ${theme.secondary})` }} />
        <div className="flex flex-wrap items-start justify-between gap-6 p-5">
          <div className="flex items-start gap-4">
            <Link to={`/orgs/${parentBref}`} className="grid h-9 w-9 place-items-center rounded-md border border-ink-700 text-ink-400 transition-colors hover:border-ink-500 hover:text-ink-100">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <div className="relative h-[88px] w-[88px] shrink-0 overflow-hidden rounded-md border border-ink-700 bg-ink-800" style={{ borderColor: `${accent}55` }}>
              <img src={`https://img.mlbstatic.com/mlb-photos/image/upload/d_people:generic:headshot:67:current.png/w_240,q_auto:best/v1/people/${player.mlb_player_id}/headshot/67/current`} alt={player.name ?? ''} className="h-full w-full object-cover" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">Prospect Workup</div>
              <div className="flex items-center gap-2">
                <div className="text-[26px] font-semibold tracking-tight text-ink-100">{player.name}</div>
                <span className={`chip mono ${tone === 'pos' ? 'chip-pos' : tone === 'neg' ? 'chip-neg' : ''}`}>
                  <Sparkles className="h-2.5 w-2.5" /> grade {grade} · {gradeLabel(grade)}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-ink-300">
                <span className="inline-flex items-center gap-1.5"><TeamLogo team={parentBref} size={16} /> {parentBref} affiliate · {player.team_name ?? '—'}</span>
                <span className="chip mono chip-accent">{LEVEL_LABELS[player.level]}</span>
                <span>{player.position_name ?? player.position_abbr ?? '—'}</span>
                {player.age != null && <span>· age {player.age}</span>}
                {player.height_inches != null && <span>· {Math.floor(player.height_inches / 12)}&apos;{player.height_inches % 12}&quot;</span>}
                {player.weight_lbs != null && <span>· {player.weight_lbs}lb</span>}
                {player.bat_side && <span>· {player.bat_side}HB</span>}
                {player.pitch_hand && <span>· {player.pitch_hand}HP</span>}
                {player.birth_country && <span>· {player.birth_country}</span>}
              </div>
              <div className="mt-1 text-[11px] text-ink-400">Minor leagues — no MLB Statcast on file yet.</div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip mono">{player.is_pitcher ? 'Pitcher' : 'Hitter'}</span>
            <span className="chip mono">Primary level: {player.level}</span>
            {player.top_level !== player.level && <span className="chip mono chip-accent">Reached: {player.top_level}</span>}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-ink-700 px-5 py-4 md:grid-cols-6">
          <HeroKpi label="Scout grade" value={`${grade}`} sub={gradeLabel(grade)} tone={tone} />
          {!isPitcher ? (
            <>
              <HeroKpi label="PA-weighted OPS" value={player.ops_pa_weighted != null ? player.ops_pa_weighted.toFixed(3) : '—'} sub="2024 MiLB · cross-level" tone={(player.ops_pa_weighted ?? 0) >= 0.8 ? 'pos' : (player.ops_pa_weighted ?? 0) < 0.65 ? 'neg' : 'neutral'} />
              <HeroKpi label="Plate apps" value={player.pa != null ? String(player.pa) : '—'} sub="2024 total" />
              <HeroKpi label="Home runs" value={player.hr != null ? String(player.hr) : '—'} sub="2024 total" />
              <HeroKpi label="K-rate" value={player.pa && player.k != null ? `${((player.k / player.pa) * 100).toFixed(1)}%` : '—'} sub="strikeout rate" />
              <HeroKpi label="BB-rate" value={player.pa && player.bb != null ? `${((player.bb / player.pa) * 100).toFixed(1)}%` : '—'} sub="walk rate" />
            </>
          ) : (
            <>
              <HeroKpi label="IP-weighted ERA" value={player.era_ip_weighted != null ? player.era_ip_weighted.toFixed(2) : '—'} sub="2024 MiLB · cross-level" tone={(player.era_ip_weighted ?? 99) <= 3.5 ? 'pos' : (player.era_ip_weighted ?? 99) >= 5 ? 'neg' : 'neutral'} />
              <HeroKpi label="Innings" value={player.ip != null ? String(player.ip) : '—'} sub="2024 total" />
              <HeroKpi label="Strikeouts" value={player.k != null ? String(player.k) : '—'} sub="2024 total" />
              <HeroKpi label="K/9" value={player.ip && player.k != null ? ((player.k / player.ip) * 9).toFixed(1) : '—'} sub="rate stat" />
              <HeroKpi label="BB/9" value={player.ip && player.bb != null ? ((player.bb / player.ip) * 9).toFixed(1) : '—'} sub="rate stat" />
            </>
          )}
        </div>
      </motion.div>

      <div className="card p-5 text-[13px] leading-relaxed text-ink-300">
        <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Why this grade</div>
        <p>
          The scout-grade proxy combines <strong className="text-ink-100">age vs typical-for-level</strong>{' '}
          (a {player.age ?? '?'}-yr-old at {player.level} is{' '}
          {player.age != null ? (player.age < (player.level === 'AAA' ? 25 : player.level === 'AA' ? 23 : player.level === 'A+' ? 22 : 21) ? 'young' : 'old') : 'of indeterminate age'}{' '}
          for the level), <strong className="text-ink-100">performance vs level baseline</strong>{' '}
          ({isPitcher ? 'IP-weighted ERA' : 'PA-weighted OPS'} of {isPitcher ? (player.era_ip_weighted ?? 0).toFixed(2) : (player.ops_pa_weighted ?? 0).toFixed(3)}),
          and <strong className="text-ink-100">reach</strong>{' '}
          (highest level touched in 2024 was {player.top_level}).
          Final value: <span className="mono tabular text-ink-100">{grade}</span> on the standard 20-80 scale —{' '}
          <span className={tone === 'pos' ? 'text-positive-500' : tone === 'neg' ? 'text-negative-500' : 'text-ink-200'}>{gradeLabel(grade)}</span>.
        </p>
        <p className="mt-2 text-[11.5px] text-ink-400">
          Synthetic proxy only. V2 will integrate Baseball America / FanGraphs grades when those ingests land. No fingerprint comps available without MLB Statcast.
        </p>
      </div>

      <div className="mt-6 text-[11px] text-ink-400">
        <span className="mono">Farm-only profile · MiLB aggregate 2024 · {player.mlb_player_id}</span>
      </div>
    </main>
  )
}
