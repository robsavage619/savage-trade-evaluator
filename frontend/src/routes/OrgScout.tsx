import { useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine, LineChart, Line, ScatterChart, Scatter, CartesianGrid, BarChart, Bar } from 'recharts'
import { ArrowLeft, ArrowRight, Brain, Trophy, AlertTriangle, Terminal, Copy, ClipboardCheck, X, CheckCircle2, AlertCircle, RotateCcw, GitCompare, Sparkles, TrendingUp, Coins, Trees, Activity, Users, Search, ChevronDown, ChevronUp, Sprout, Star } from 'lucide-react'
import { getOrgProfile, orgProfiles } from '../data/orgs'
import { useIdentityStore, TEAM_THEME } from '../lib/identityStore'
import { useRoster, useTeamsByBref } from '../lib/rosterStore'
import { TeamLogo } from '../components/TeamLogo'
import { Section, Stat } from '../components/Section'
import { teamColor, fmtSigned, fmtMoney } from '../lib/format'
import { composeOrgScoutPrompt } from '../lib/composeOrgScout'
import { useReasoningStore, parseReasoningResponse } from '../lib/reasoningStore'
import { useFarmForOrg } from '../lib/farmStore'
import { FarmSystem } from '../components/FarmSystem'

const SCOUT_BASE = -2_000_000

export default function OrgScout() {
  const params = useParams<{ bref: string }>()
  const bref = (params.bref ?? '').toUpperCase()
  const profile = getOrgProfile(bref)
  if (!profile) return <Navigate to="/orgs" replace />

  const roster = useRoster()
  const teamsByBref = useTeamsByBref()
  const yourBref = useIdentityStore((s) => s.activeTeam)
  const yourProfile = getOrgProfile(yourBref)
  const team = teamsByBref[bref]
  const yourTeam = teamsByBref[yourBref]
  const theme = TEAM_THEME[bref] ?? TEAM_THEME.NYM
  const teamMeta = roster.teams.find((t) => t.bref === bref)
  const teamName = teamMeta?.name ?? bref
  const farm = useFarmForOrg(bref)

  const [compare, setCompare] = useState(false)
  const isSelf = bref === yourBref

  // Build positional WAR rank vs league for current roster
  const posBreakdown = useMemo(() => buildPositionalBreakdown(teamMeta?.players ?? []), [teamMeta])

  // Scout brief drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [paste, setPaste] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)
  const [pasteOk, setPasteOk] = useState(false)
  const [copied, setCopied] = useState(false)
  const scoutId = SCOUT_BASE - hash(`${yourBref}::${bref}`)
  const override = useReasoningStore((s) => s.overrides[scoutId])
  const setReasoning = useReasoningStore((s) => s.set)

  const prompt = useMemo(() => composeOrgScoutPrompt({ profile, teamName, yourBref }), [profile, teamName, yourBref])

  async function copyPrompt() {
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  function applyPaste() {
    setPasteError(null)
    setPasteOk(false)
    const r = parseReasoningResponse(paste)
    if ('error' in r) { setPasteError(r.error); return }
    setReasoning(scoutId, r, `Claude Code · scout ${bref}`)
    setPasteOk(true)
  }

  // Trajectory data (with optional compare overlay)
  const trajectoryData = profile.trajectory.map((t) => {
    const row: Record<string, number | null> = {
      season: t.season,
      wins: t.wins,
      war: t.war_total,
      runDiff: t.runs_scored != null && t.runs_allowed != null ? t.runs_scored - t.runs_allowed : null,
    }
    if (compare && yourProfile) {
      const m = yourProfile.trajectory.find((x) => x.season === t.season)
      row.youWins = m?.wins ?? null
      row.youWar = m?.war_total ?? null
    }
    return row
  })

  // Org placement scatter — use all 30 placements
  const placementData = Object.values(orgProfiles)
    .map((p) => p.org_placement && p.org_placement.dev_war != null && p.org_placement.mean_surplus != null
      ? { team: p.bref, dev: p.org_placement.dev_war, surplus: p.org_placement.mean_surplus, n: p.org_placement.n_trades ?? 0 }
      : null)
    .filter((x): x is { team: string; dev: number; surplus: number; n: number } => x !== null)

  return (
    <main className="mx-auto max-w-[1640px] px-6 py-6">
      {/* Hero band */}
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="card relative mb-6 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-1 w-full" style={{ background: `linear-gradient(90deg, ${theme.primary}, ${theme.secondary})` }} />
        <div className="flex flex-wrap items-start justify-between gap-6 p-5">
          <div className="flex items-center gap-4">
            <Link to="/orgs" className="grid h-9 w-9 place-items-center rounded-md border border-ink-700 text-ink-400 transition-colors hover:border-ink-500 hover:text-ink-100">
              <ArrowLeft className="h-4 w-4" />
            </Link>
            <TeamLogo team={bref} size={64} />
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">Org Scout</div>
              <div className="text-[24px] font-semibold tracking-tight text-ink-100">{teamName}</div>
              <div className="mt-0.5 text-[12px] text-ink-400">
                Full scouting profile · {profile.trajectory.length}-yr trajectory · {profile.trade_dna.summary?.n_trades ?? 0} trades on file
                {isSelf ? <span className="ml-2 chip chip-accent mono">your team</span> : null}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {!isSelf && yourProfile && (
              <button
                onClick={() => setCompare((v) => !v)}
                className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition-colors ${compare ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-200 hover:border-ink-500'}`}
              >
                <GitCompare className="h-3 w-3" /> Compare vs {yourBref}
              </button>
            )}
            <button
              onClick={() => setDrawerOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 transition-colors hover:bg-accent-400"
            >
              <Terminal className="h-3.5 w-3.5" /> Scout brief with Claude Code
            </button>
          </div>
        </div>
        {/* Hero KPIs */}
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 border-t border-ink-700 px-5 py-4 md:grid-cols-6">
          <HeroKpi label="Last record" value={lastRecord(profile)} sub="W-L · last completed season" />
          <HeroKpi label="bWAR trend (3yr)" value={trendArrow(profile)} sub="vs 3-season prior" />
          <HeroKpi label="Pitcher K%-jump norm" value={profile.dev_signature.avg_pitcher_k_jump_3yr != null ? `${profile.dev_signature.avg_pitcher_k_jump_3yr >= 0 ? '+' : ''}${profile.dev_signature.avg_pitcher_k_jump_3yr.toFixed(1)} pp` : '—'} sub="5-yr avg · pitchers acquired" tone={(profile.dev_signature.avg_pitcher_k_jump_3yr ?? 0) > 3 ? 'pos' : (profile.dev_signature.avg_pitcher_k_jump_3yr ?? 0) < 0 ? 'neg' : 'neutral'} />
          <HeroKpi label="Hitter xwOBA-jump norm" value={profile.dev_signature.avg_hitter_xwoba_jump_3yr != null ? `${profile.dev_signature.avg_hitter_xwoba_jump_3yr >= 0 ? '+' : ''}${profile.dev_signature.avg_hitter_xwoba_jump_3yr.toFixed(3)}` : '—'} sub="5-yr avg · hitters acquired" tone={(profile.dev_signature.avg_hitter_xwoba_jump_3yr ?? 0) > 0 ? 'pos' : 'neg'} />
          <HeroKpi label="Mean trade surplus" value={profile.trade_dna.summary?.mean_surplus != null ? fmtSigned(profile.trade_dna.summary.mean_surplus) : '—'} sub={`${profile.trade_dna.summary?.n_trades ?? 0} trades on file (3yr)`} tone={(profile.trade_dna.summary?.mean_surplus ?? 0) >= 0 ? 'pos' : 'neg'} />
          <HeroKpi label="GM win rate" value={profile.trade_dna.summary ? `${Math.round(((profile.trade_dna.summary.n_positive ?? 0) / (profile.trade_dna.summary.n_trades || 1)) * 100)}%` : '—'} sub="P(surplus > 0)" />
        </div>
      </motion.div>

      {override?.reasoning ? (
        <ScoutAnalysisCard reasoning={override.reasoning} savedAt={override.savedAt} />
      ) : null}

      {/* Body */}
      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        {/* Trajectory */}
        <Section eyebrow="Trajectory" title="10-year team performance" hint="Wins, run differential, team WAR. Compare overlay on toggle.">
          <div className="card p-4">
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={trajectoryData} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                <defs>
                  <linearGradient id="grad-wins" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor={theme.primary} stopOpacity={0.5} />
                    <stop offset="100%" stopColor={theme.primary} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="season" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} domain={[40, 110]} />
                <Tooltip contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }} />
                <ReferenceLine y={81} stroke="rgba(138,150,192,0.25)" strokeDasharray="3 3" />
                <Area type="monotone" dataKey="wins" stroke={theme.primary} fill="url(#grad-wins)" strokeWidth={2.2} name={`${bref} wins`} />
                {compare && <Line type="monotone" dataKey="youWins" stroke="#ff8a3d" strokeDasharray="4 3" strokeWidth={2} dot={false} name={`${yourBref} wins`} />}
              </AreaChart>
            </ResponsiveContainer>
            <div className="mt-3 grid grid-cols-3 gap-3 text-[11px] text-ink-400">
              <div><span className="text-ink-200">Run diff (last 3 avg):</span> <span className="mono tabular text-ink-100">{recentRunDiff(profile)}</span></div>
              <div><span className="text-ink-200">Team WAR (last):</span> <span className="mono tabular text-ink-100">{lastWar(profile)}</span></div>
              <div><span className="text-ink-200">Trajectory phase:</span> <span className="mono text-accent-300">{trajectoryPhase(profile)}</span></div>
            </div>
          </div>
        </Section>

        {/* Dev signature panel */}
        <Section eyebrow="Dev Signature" title="What this org does to incoming talent" hint="The differentiator — if you trade with them, this is the multiplier on acquirer-column value.">
          <div className="card p-4">
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={profile.dev_signature.history.slice(0, 8).reverse()} margin={{ top: 8, right: 12, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                <XAxis dataKey="season" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} unit=" pp" />
                <Tooltip contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }} />
                <ReferenceLine y={0} stroke="rgba(138,150,192,0.3)" />
                <Bar dataKey="org_pitcher_k_jump_3yr" fill={theme.primary} name="Pitcher K%-jump (pp)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="mt-3 text-[11px] text-ink-400">
              Bars = year-over-year K% percentile gain for pitchers this org acquired or developed. Sustained positive values = a real dev infrastructure. Negative = reverse-Strom.
            </div>
          </div>
        </Section>

        {/* Payroll Stack — Spotrac team totals */}
        {profile.spotrac_payroll && profile.spotrac_payroll.length > 0 ? (
          <Section eyebrow="Payroll Stack" title={`Active · dead · injured · ${profile.spotrac_payroll[0]?.season ?? ''}`} hint="Spotrac team-payroll snapshot — CBT-relevant breakdown for the current book.">
            <PayrollStack rows={profile.spotrac_payroll} contractBreakdown={profile.contract_breakdown ?? []} themeColor={theme.primary} />
          </Section>
        ) : null}

        {/* Full 40-man */}
        <Section eyebrow="40-Man Roster" title={`Every active player · ${teamMeta?.players.length ?? 0} on the books`} hint="Live MLB Stats API roster. Sort + filter. Every row links to the full player workup.">
          <FullRosterTable players={teamMeta?.players ?? []} bref={bref} />
        </Section>

        {/* Farm System */}
        <Section
          eyebrow="Farm System"
          title={`Affiliates · ${farm ? `${countFarm(farm)} players` : 'no data'}`}
          hint="2024 MiLB stats re-bucketed by current (2026) affiliation — players acquired via trade since 2024 carry a chip showing their former org."
        >
          <FarmSystem farm={farm} themeColor={theme.primary} />
        </Section>

        {/* Payroll */}
        <Section eyebrow="Payroll" title={`Top contracts · ${profile.payroll.season ?? 'latest'}`} hint="Salary structure of the highest-paid roster spots — proxy for trade flexibility.">
          <div className="card overflow-hidden">
            {profile.payroll.top_contracts.length === 0 ? (
              <div className="grid place-items-center p-8 text-[12px] text-ink-400">No payroll data for this org.</div>
            ) : (
              <table className="w-full text-[12px]">
                <thead className="bg-ink-800 text-[10px] uppercase tracking-[0.12em] text-ink-400">
                  <tr>
                    <th className="px-3 py-2 text-left">Player</th>
                    <th className="px-3 py-2">Role</th>
                    <th className="px-3 py-2 text-right">WAR</th>
                    <th className="px-3 py-2 text-right">Salary</th>
                    <th className="px-3 py-2 text-right">$/WAR</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-700/60">
                  {profile.payroll.top_contracts.map((c) => {
                    const efficient = c.war != null && c.war > 0 && c.salary != null ? c.salary / c.war / 1_000_000 : null
                    return (
                      <tr key={c.mlb_id} className="group cursor-pointer hover:bg-ink-800/40" onClick={() => { window.location.href = `/player/${c.mlb_id}` }}>
                        <td className="px-3 py-2 font-medium text-ink-100 group-hover:text-accent-300">{c.name_common}</td>
                        <td className="px-3 py-2 text-center"><span className={`mono rounded px-1.5 py-0.5 text-[10px] ${c.role === 'P' ? 'bg-baseline-500/15 text-baseline-500' : 'bg-accent-500/15 text-accent-300'}`}>{c.role}</span></td>
                        <td className={`px-3 py-2 text-right mono tabular ${c.war != null ? (c.war >= 0 ? 'text-positive-500' : 'text-negative-500') : 'text-ink-400'}`}>{c.war != null ? fmtSigned(c.war, 1) : '—'}</td>
                        <td className="px-3 py-2 text-right mono tabular text-ink-200">{c.salary != null ? fmtMoney(c.salary) : '—'}</td>
                        <td className="px-3 py-2 text-right mono tabular text-ink-300">{efficient != null ? `$${efficient.toFixed(1)}M` : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
          </div>
        </Section>

        {/* Age curve */}
        <Section eyebrow="Aging Curve" title="WAR by age — where the value lives" hint="Each dot = a player; size = WAR. Watch for age-cliffs in the core.">
          <AgeCurveChart rows={profile.age_curve} themeColor={theme.primary} />
        </Section>

        {/* Trade DNA */}
        <Section eyebrow="Trade DNA" title="How this GM transacts" hint="Last 12 trades by impact; mean surplus characterizes their model-vs-baseline edge.">
          <div className="card overflow-hidden">
            <div className="flex items-center justify-between border-b border-ink-700 px-3 py-2 text-[11px] text-ink-300">
              <span>{profile.trade_dna.summary?.n_trades ?? 0} trades on file · positive: {profile.trade_dna.summary?.n_positive ?? 0}</span>
              <span className={`mono tabular ${(profile.trade_dna.summary?.mean_surplus ?? 0) >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>mean {fmtSigned(profile.trade_dna.summary?.mean_surplus ?? 0)}</span>
            </div>
            <ul className="max-h-[300px] divide-y divide-ink-700/50 overflow-y-auto">
              {profile.trade_dna.recent.map((t) => (
                <li key={t.trade_event_id} className="px-3 py-2 text-[12px]">
                  <Link to={`/trade/${t.trade_event_id}`} className="block group">
                    <div className="flex items-center justify-between">
                      <span className="mono text-[10px] tabular text-ink-400">{t.trade_season}</span>
                      <span className={`mono tabular ${t.surplus >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>{fmtSigned(t.surplus)}</span>
                    </div>
                    <div className="mt-0.5 text-ink-200 line-clamp-2 group-hover:text-ink-100">
                      received <span className="text-ink-100">{t.players_received || '—'}</span> for <span className="text-ink-100">{t.players_given_up || '—'}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </Section>

        {/* Org placement on 2D map */}
        <Section eyebrow="Org Placement" title="Where they sit on the dev / trade-quality map" hint="2D placement vs the rest of MLB. Top-right = elite at both.">
          <div className="card p-4">
            <ResponsiveContainer width="100%" height={280}>
              <ScatterChart margin={{ top: 8, right: 12, bottom: 28, left: 28 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
                <XAxis type="number" dataKey="dev" stroke="#5a6896" tick={{ fontSize: 11 }} tickFormatter={(v: number) => v.toFixed(0)} name="Dev WAR" />
                <YAxis type="number" dataKey="surplus" stroke="#5a6896" tick={{ fontSize: 11 }} tickFormatter={(v: number) => v.toFixed(1)} name="Mean surplus" />
                <Tooltip content={({ payload }) => {
                  const p = payload?.[0]?.payload
                  if (!p) return null
                  return <div className="card px-3 py-2 text-[11px]"><div className="font-semibold text-ink-100">{p.team}</div><div className="mono mt-1 tabular text-ink-300">Dev {p.dev.toFixed(1)} · Surplus {fmtSigned(p.surplus)} · n={p.n}</div></div>
                }} />
                {placementData.map((d) => (
                  <Scatter key={d.team} data={[d]} shape={(props: { cx?: number; cy?: number }) => {
                    const cx = props.cx ?? 0, cy = props.cy ?? 0
                    const sz = d.team === bref ? 26 : d.team === yourBref ? 22 : 18
                    return (
                      <g>
                        <circle cx={cx} cy={cy} r={sz / 2 + 2} fill={d.team === bref ? 'rgba(255,106,19,0.25)' : 'rgba(11,16,24,0.6)'} stroke={d.team === bref ? '#ff6a13' : d.team === yourBref ? '#3ddc97' : 'rgba(255,255,255,0.08)'} strokeWidth={d.team === bref || d.team === yourBref ? 2 : 1} />
                        <image href={`https://www.mlbstatic.com/team-logos/${teamMlbId(d.team)}.svg`} x={cx - sz/2} y={cy - sz/2} width={sz} height={sz} />
                      </g>
                    )
                  }} />
                ))}
              </ScatterChart>
            </ResponsiveContainer>
            <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-400">
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-accent-500" /> {bref} (focus)</span>
              {!isSelf && <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-positive-500" /> {yourBref} (you)</span>}
            </div>
          </div>
        </Section>

        {/* FO continuity */}
        <Section eyebrow="Decision-Makers" title="Front office continuity (5 yr)" hint="Stable orgs trade differently than rebuilding ones.">
          <FoTimeline fo={profile.fo_history} themeColor={theme.primary} />
        </Section>

        {/* Positional WAR breakdown */}
        <Section eyebrow="Roster Composition" title="40-man by position group" hint="Sourced from live MLB Stats API roster.">
          <div className="card p-4">
            <PosBars breakdown={posBreakdown} themeColor={theme.primary} />
          </div>
        </Section>
      </div>

      <div className="mt-6 text-[11px] text-ink-400">
        <span className="mono">Org Scout v0.1 · 10-yr trajectory · dev signature · trade DNA · personnel · positional depth · 2D org placement · roster from {new Date(roster.refreshed_at).toLocaleDateString()}</span>
      </div>

      {/* Scout brief drawer */}
      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} onClick={() => setDrawerOpen(false)} />
            <motion.aside initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', stiffness: 300, damping: 32 }} className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-ink-700 bg-ink-900">
              <header className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400"><Terminal className="h-4 w-4" /></div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Scout brief with Claude Code</div>
                    <div className="text-[14px] font-semibold text-ink-100">{bref} · {teamName}</div>
                  </div>
                </div>
                <button onClick={() => setDrawerOpen(false)} className="rounded-md p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100"><X className="h-4 w-4" /></button>
              </header>
              <div className="flex-1 overflow-y-auto p-5">
                <section className="mb-5">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 1 · Generated prompt</div>
                      <div className="text-[12px] text-ink-300">Bundles 10-yr trajectory, dev signature, trade DNA, FO, and top contracts.</div>
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
                  {pasteOk && <div className="mt-2 flex items-center gap-2 rounded-md border border-positive-500/40 bg-positive-500/10 px-3 py-2 text-[12px] text-positive-500"><CheckCircle2 className="h-3.5 w-3.5" /> Brief applied — see the Analysis card at the top of the scout page.</div>}
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

function ScoutAnalysisCard({ reasoning, savedAt }: { reasoning: import('../data/pipeline').AiReasoning; savedAt: string }) {
  return (
    <div className="card mb-6 p-5">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Claude scout brief</div>
          <div className="text-[15px] font-semibold leading-snug text-ink-100">{reasoning.headline}</div>
        </div>
        <span className="chip chip-pos mono">applied {new Date(savedAt).toLocaleString()}</span>
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-[1fr_280px]">
        <div className="space-y-3 text-[13px] leading-relaxed text-ink-200">
          <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Thesis</div><p className="mt-1">{reasoning.thesis}</p></div>
          <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Key drivers</div>
            <ul className="mt-1 space-y-2">{reasoning.keyDrivers.map((d, i) => (
              <li key={i} className="rounded-md border border-ink-700 bg-ink-800/40 p-2.5">
                <div className="flex items-center gap-2">{d.chip && <span className="chip chip-accent mono">{d.chip}</span>}<span className="text-[12.5px] font-semibold text-ink-100">{d.title}</span></div>
                <div className="mt-1 text-[12px] text-ink-300">{d.body}</div>
              </li>
            ))}</ul>
          </div>
          <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Recommendation</div><p className="mt-1 font-semibold text-ink-100">{reasoning.recommendation}</p></div>
        </div>
        <div className="space-y-3 border-l border-ink-700 pl-4">
          <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Watch-outs</div>
            <ul className="mt-1 space-y-2 text-[11px]">{reasoning.watchOuts.map((w, i) => (
              <li key={i} className="rounded-md bg-negative-500/[0.06] p-2"><div className="font-semibold text-ink-100">{w.title}</div><div className="mt-0.5 text-ink-300">{w.body}</div></li>
            ))}</ul>
          </div>
          <div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Grounding</div>
            <ul className="mt-1 space-y-2 text-[11px]">{reasoning.citations.map((c, i) => (
              <li key={i} className="rounded-md border border-ink-700 bg-ink-800/60 p-2"><div className="mono font-semibold text-accent-300">[{i + 1}] {c.label}</div><div className="mt-0.5 text-ink-300">{c.detail}</div></li>
            ))}</ul>
          </div>
        </div>
      </div>
    </div>
  )
}

function AgeCurveChart({ rows, themeColor }: { rows: import('../data/orgs').AgeCurveRow[]; themeColor: string }) {
  const data = rows.filter((r) => r.age != null && r.war != null).map((r) => ({
    age: r.age!,
    war: r.war,
    name: r.full_name,
    role: r.role,
  }))
  if (data.length === 0) return <div className="card p-4 text-[12px] text-ink-400">No age-curve data.</div>
  const meanAge = data.reduce((a, b) => a + b.age * Math.max(0, b.war), 0) / data.reduce((a, b) => a + Math.max(0, b.war), 1)
  return (
    <div className="card p-4">
      <ResponsiveContainer width="100%" height={260}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 28, left: 28 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.08)" />
          <XAxis dataKey="age" type="number" domain={[18, 42]} stroke="#5a6896" tick={{ fontSize: 11 }} name="Age" />
          <YAxis dataKey="war" type="number" stroke="#5a6896" tick={{ fontSize: 11 }} name="WAR" />
          <ReferenceLine x={meanAge} stroke="rgba(138,150,192,0.4)" strokeDasharray="3 3" label={{ value: `WAR-weighted age ${meanAge.toFixed(1)}`, fill: '#8a96c0', fontSize: 10 }} />
          <Tooltip content={({ payload }) => {
            const p = payload?.[0]?.payload
            if (!p) return null
            return <div className="card px-3 py-2 text-[11px]"><div className="font-semibold text-ink-100">{p.name}</div><div className="mono mt-1 tabular text-ink-300">Age {p.age} · {fmtSigned(p.war, 1)} WAR · {p.role}</div></div>
          }} />
          <Scatter data={data.filter((d) => d.role === 'B')} fill={themeColor} fillOpacity={0.85} name="Hitters" />
          <Scatter data={data.filter((d) => d.role === 'P')} fill="#6699ff" fillOpacity={0.85} name="Pitchers" />
        </ScatterChart>
      </ResponsiveContainer>
      <div className="mt-2 flex items-center gap-3 text-[11px] text-ink-400">
        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: themeColor }} /> hitters</span>
        <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-baseline-500" /> pitchers</span>
        <span className="ml-auto">{data.length} player-seasons</span>
      </div>
    </div>
  )
}

function FoTimeline({ fo, themeColor }: { fo: import('../data/orgs').FoEntry[]; themeColor: string }) {
  // Build per-role timeline of seasons → person
  const ROLES = ['President', 'General Manager', 'Manager', 'Farm Director', 'Scouting Director']
  const seasons = [...new Set(fo.map((f) => f.season))].sort((a, b) => a - b)
  const grid: Record<string, Record<number, string>> = {}
  for (const role of ROLES) grid[role] = {}
  for (const f of fo) grid[f.role][f.season] = f.person_name
  return (
    <div className="card overflow-hidden">
      <table className="w-full text-[11px]">
        <thead className="bg-ink-800 text-[10px] uppercase tracking-[0.12em] text-ink-400">
          <tr>
            <th className="px-3 py-2 text-left">Role</th>
            {seasons.map((s) => <th key={s} className="px-2 py-2 text-right mono tabular">{s}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700/60">
          {ROLES.map((role) => {
            const cells = seasons.map((s) => grid[role][s] ?? '')
            return (
              <tr key={role}>
                <td className="px-3 py-2 font-medium text-ink-200">{role}</td>
                {cells.map((name, i) => {
                  const prev = i > 0 ? cells[i - 1] : ''
                  const change = name && prev && name !== prev
                  return (
                    <td key={i} className={`px-2 py-2 text-right mono text-[10.5px] truncate max-w-[110px] ${change ? 'border-l border-accent-500/50' : ''}`} style={change ? { background: 'rgba(255,138,61,0.08)' } : undefined}>
                      <span className="text-ink-100" title={name}>{name.split(' ').slice(-1)[0] || '—'}</span>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="border-t border-ink-700 px-3 py-2 text-[10.5px] text-ink-400">
        Highlighted cells = regime change. Continuity bands = retained leadership.
      </div>
    </div>
  )
}

function PosBars({ breakdown, themeColor }: { breakdown: Array<{ label: string; count: number }>; themeColor: string }) {
  const max = Math.max(...breakdown.map((b) => b.count), 1)
  return (
    <div className="space-y-2.5">
      {breakdown.map((b) => (
        <div key={b.label} className="flex items-center gap-3">
          <div className="w-28 text-[11px] text-ink-300">{b.label}</div>
          <div className="relative h-5 flex-1 overflow-hidden rounded-md bg-ink-800/70">
            <div className="absolute inset-y-0 left-0 rounded-md" style={{ width: `${(b.count / max) * 100}%`, background: themeColor, opacity: 0.85 }} />
            <span className="absolute right-1.5 top-1/2 -translate-y-1/2 mono text-[11px] tabular text-ink-100">{b.count}</span>
          </div>
        </div>
      ))}
    </div>
  )
}

function buildPositionalBreakdown(players: import('../data/players').CurrentPlayer[]) {
  const groups = { Pitcher: 0, Catcher: 0, Infield: 0, Outfield: 0, 'DH/Other': 0 }
  for (const p of players) {
    const code = p.position_code
    if (code === '1') groups.Pitcher++
    else if (code === '2') groups.Catcher++
    else if (['3', '4', '5', '6'].includes(code ?? '')) groups.Infield++
    else if (['7', '8', '9', 'O'].includes(code ?? '')) groups.Outfield++
    else groups['DH/Other']++
  }
  return Object.entries(groups).map(([label, count]) => ({ label, count }))
}

function lastRecord(p: import('../data/orgs').OrgProfile): string {
  const last = [...p.trajectory].reverse().find((r) => r.wins != null && r.losses != null)
  return last ? `${last.wins}-${last.losses}` : '—'
}

function lastWar(p: import('../data/orgs').OrgProfile): string {
  const last = [...p.trajectory].reverse().find((r) => r.war_total != null)
  return last?.war_total != null ? `${last.war_total.toFixed(1)}` : '—'
}

function recentRunDiff(p: import('../data/orgs').OrgProfile): string {
  const recent = [...p.trajectory].reverse().slice(0, 3).filter((r) => r.runs_scored != null && r.runs_allowed != null)
  if (recent.length === 0) return '—'
  const mean = recent.reduce((a, r) => a + ((r.runs_scored ?? 0) - (r.runs_allowed ?? 0)), 0) / recent.length
  return `${mean >= 0 ? '+' : ''}${mean.toFixed(0)}`
}

function trendArrow(p: import('../data/orgs').OrgProfile): string {
  const wars = p.trajectory.filter((r) => r.war_total != null).slice(-3).map((r) => r.war_total!)
  if (wars.length < 2) return '—'
  const delta = wars[wars.length - 1] - wars[0]
  return `${delta >= 0 ? '▲' : '▼'} ${Math.abs(delta).toFixed(1)} WAR`
}

function trajectoryPhase(p: import('../data/orgs').OrgProfile): string {
  const recent = p.trajectory.filter((r) => r.wins != null).slice(-3)
  if (recent.length === 0) return 'unknown'
  const meanWins = recent.reduce((a, r) => a + (r.wins ?? 0), 0) / recent.length
  if (meanWins >= 92) return 'win-now'
  if (meanWins >= 84) return 'contending'
  if (meanWins >= 75) return 'bridge'
  return 'rebuilding'
}

function hash(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

function teamMlbId(bref: string): number {
  const M: Record<string, number> = { ARI:109,ATL:144,BAL:110,BOS:111,CHC:112,CHW:145,CIN:113,CLE:114,COL:115,DET:116,HOU:117,KCR:118,LAA:108,LAD:119,MIA:146,MIL:158,MIN:142,NYM:121,NYY:147,OAK:133,PHI:143,PIT:134,SDP:135,SEA:136,SFG:137,STL:138,TBR:139,TEX:140,TOR:141,WSN:120 }
  return M[bref] ?? 121
}

// ───────────────────────────────────────────────────────── extra sections
function PayrollStack({ rows, contractBreakdown, themeColor }: { rows: import('../data/orgs').SpotracPayrollRow[]; contractBreakdown: import('../data/orgs').ContractBreakdownRow[]; themeColor: string }) {
  const latest = rows[0]
  if (!latest) return <div className="card p-4 text-[12px] text-ink-400">No Spotrac data.</div>
  const total = latest.total_payroll ?? 0
  const seg = (v: number | null) => total > 0 && v != null ? (v / total) * 100 : 0
  return (
    <div className="grid gap-4 md:grid-cols-[1.2fr_1fr]">
      <div className="card p-4">
        <div className="mb-3 flex items-baseline justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">Total payroll · {latest.season}</div>
            <div className="mono text-[24px] font-semibold tabular text-ink-100">${(total / 1e6).toFixed(1)}M</div>
            <div className="text-[11px] text-ink-400">{latest.active_players ?? '—'} players on the active book</div>
          </div>
          <div className="text-right text-[11px] text-ink-400">
            <div>CBT 1st tier <span className="mono tabular text-ink-200">~$237M</span></div>
            <div>CBT 2nd tier <span className="mono tabular text-ink-200">~$257M</span></div>
          </div>
        </div>
        <div className="relative h-7 w-full overflow-hidden rounded-md bg-ink-800">
          <div className="absolute inset-y-0 left-0 bg-positive-500/70" style={{ width: `${seg(latest.active_payroll)}%` }} title="Active payroll" />
          <div className="absolute inset-y-0 bg-baseline-500/70" style={{ left: `${seg(latest.active_payroll)}%`, width: `${seg(latest.injured_payroll)}%` }} title="Injured payroll" />
          <div className="absolute inset-y-0 bg-negative-500/70" style={{ left: `${seg(latest.active_payroll) + seg(latest.injured_payroll)}%`, width: `${seg(latest.dead_money)}%` }} title="Dead money" />
          <div className="absolute inset-y-0 border-l border-dashed border-ink-400" style={{ left: `${total > 0 ? (237_000_000 / total) * 100 : 100}%` }} />
        </div>
        <div className="mt-3 grid grid-cols-3 gap-3 text-[11px]">
          <Seg color="bg-positive-500" label="Active" value={latest.active_payroll} />
          <Seg color="bg-baseline-500" label="Injured" value={latest.injured_payroll} />
          <Seg color="bg-negative-500" label="Dead" value={latest.dead_money} />
        </div>
      </div>
      <div className="card p-4">
        <div className="mb-2 text-[10px] uppercase tracking-[0.14em] text-ink-400">Contract phase mix · {latest.season}</div>
        {contractBreakdown.length === 0 ? <div className="text-[12px] text-ink-400">No phase breakdown.</div> : (
          <div className="space-y-1.5">
            {contractBreakdown.slice(0, 6).map((c) => {
              const tot = contractBreakdown.reduce((a, x) => a + (x.total_cap ?? 0), 0)
              const pct = tot > 0 && c.total_cap != null ? (c.total_cap / tot) * 100 : 0
              return (
                <div key={c.status}>
                  <div className="flex items-baseline justify-between text-[11px]">
                    <span className="text-ink-200">{c.status}</span>
                    <span className="mono tabular text-ink-300">{c.n}p · ${((c.total_cap ?? 0) / 1e6).toFixed(1)}M{c.avg_svc != null ? ` · ${c.avg_svc.toFixed(1)} yr svc` : ''}</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
                    <div className="h-full" style={{ width: `${pct}%`, background: themeColor }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function Seg({ color, label, value }: { color: string; label: string; value: number | null }) {
  return (
    <div>
      <div className="mb-0.5 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.12em] text-ink-400">
        <span className={`inline-block h-2 w-2 rounded-full ${color}`} />{label}
      </div>
      <div className="mono text-[13px] font-semibold tabular text-ink-100">${((value ?? 0) / 1e6).toFixed(1)}M</div>
    </div>
  )
}

type RosterSortKey = 'pos' | 'name' | 'age' | 'war' | 'cap' | 'svc' | 'status'

function FullRosterTable({ players, bref }: { players: import('../data/players').CurrentPlayer[]; bref: string }) {
  const [sortKey, setSortKey] = useState<RosterSortKey>('cap')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [filter, setFilter] = useState<'all' | 'pitcher' | 'hitter' | 'injured'>('all')
  const [query, setQuery] = useState('')

  const sorted = useMemo(() => {
    const q = query.trim().toLowerCase()
    let arr = players.filter((p) => {
      if (filter === 'pitcher' && p.position_code !== '1') return false
      if (filter === 'hitter' && p.position_code === '1') return false
      if (filter === 'injured' && !(p.status_code && p.status_code.startsWith('D'))) return false
      if (q && !`${p.name} ${p.position_abbr ?? ''}`.toLowerCase().includes(q)) return false
      return true
    })
    const get = (p: import('../data/players').CurrentPlayer): number | string => {
      switch (sortKey) {
        case 'pos': return p.position_code ?? ''
        case 'name': return p.name.toLowerCase()
        case 'age': return p.age ?? 0
        case 'war': return p.last_war ?? -99
        case 'cap': return p.cap_hit ?? p.last_salary ?? 0
        case 'svc': return p.service_time ?? 0
        case 'status': return p.status_code ?? ''
      }
    }
    arr = [...arr].sort((a, b) => {
      const av = get(a), bv = get(b)
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return arr
  }, [players, sortKey, sortDir, filter, query])

  const click = (k: RosterSortKey) => {
    if (k === sortKey) setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    else { setSortKey(k); setSortDir(k === 'name' || k === 'pos' ? 'asc' : 'desc') }
  }

  const SortHead = ({ k, children, align = 'right' }: { k: RosterSortKey; children: React.ReactNode; align?: 'left' | 'right' | 'center' }) => (
    <th className={`px-3 py-2 text-${align} cursor-pointer select-none hover:text-ink-100`} onClick={() => click(k)}>
      <span className="inline-flex items-center gap-1">{children}{sortKey === k ? (sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />) : null}</span>
    </th>
  )

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-700 p-3">
        <div className="relative max-w-xs flex-1">
          <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-ink-400" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search…" className="w-full rounded-md border border-ink-700 bg-ink-800/80 py-1.5 pl-7 pr-2 text-[12px] text-ink-100 placeholder:text-ink-400 focus:border-accent-500/50 focus:outline-none" />
        </div>
        <div className="flex items-center gap-1 text-[10px]">
          {(['all','pitcher','hitter','injured'] as const).map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={`rounded-full border px-2 py-0.5 uppercase tracking-wider ${filter === f ? 'border-accent-500/60 bg-accent-500/10 text-accent-300' : 'border-ink-700 text-ink-400 hover:text-ink-200'}`}>{f}</button>
          ))}
          <span className="ml-2 mono text-ink-500">{sorted.length}/{players.length}</span>
        </div>
      </div>
      <div className="max-h-[460px] overflow-y-auto">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 z-10 bg-ink-800 text-[10px] uppercase tracking-[0.12em] text-ink-400">
            <tr>
              <SortHead k="pos" align="left">Pos</SortHead>
              <SortHead k="name" align="left">Player</SortHead>
              <SortHead k="age">Age</SortHead>
              <SortHead k="war">WAR</SortHead>
              <SortHead k="cap">Cap hit</SortHead>
              <SortHead k="svc">Svc</SortHead>
              <SortHead k="status" align="center">Status</SortHead>
              <th className="px-3 py-2 text-right text-[10px] uppercase tracking-[0.12em] text-ink-400">Awards</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-700/40">
            {sorted.map((p) => {
              const cap = p.cap_hit ?? p.last_salary
              const injured = p.status_code && p.status_code.startsWith('D')
              return (
                <tr key={p.mlb_player_id} className="group cursor-pointer hover:bg-ink-800/60" onClick={() => { window.location.href = `/player/${p.mlb_player_id}` }}>
                  <td className="px-3 py-2 text-left"><span className={`mono rounded px-1.5 py-0.5 text-[10px] ${p.position_code === '1' ? 'bg-baseline-500/15 text-baseline-500' : 'bg-accent-500/15 text-accent-300'}`}>{p.position_abbr ?? '—'}</span></td>
                  <td className="px-3 py-2 font-medium text-ink-100 group-hover:text-accent-300">
                    {p.name}
                    {p.contract_status ? <span className="ml-2 text-[10px] text-ink-500">· {p.contract_status}</span> : null}
                  </td>
                  <td className="px-3 py-2 text-right mono tabular text-ink-300">{p.age ?? '—'}</td>
                  <td className={`px-3 py-2 text-right mono tabular ${p.last_war != null ? (p.last_war >= 0 ? 'text-positive-500' : 'text-negative-500') : 'text-ink-400'}`}>{p.last_war != null ? `${p.last_war >= 0 ? '+' : ''}${p.last_war.toFixed(1)}` : '—'}</td>
                  <td className="px-3 py-2 text-right mono tabular text-ink-200">{cap != null ? `$${(cap / 1e6).toFixed(1)}M` : '—'}</td>
                  <td className="px-3 py-2 text-right mono tabular text-ink-300">{p.service_time != null ? p.service_time.toFixed(1) : '—'}</td>
                  <td className="px-3 py-2 text-center">{injured ? <span className="chip chip-neg mono">{p.status_code}</span> : <span className="chip mono text-ink-300">{p.status_code ?? '—'}</span>}</td>
                  <td className="px-3 py-2 text-right">
                    {p.awards && p.awards.total > 0 ? (
                      <span className="inline-flex items-center gap-1 text-[10px]">
                        {p.awards.mvp > 0 && <span title="MVP" className="chip chip-accent mono">MVP×{p.awards.mvp}</span>}
                        {p.awards.cy_young > 0 && <span title="Cy Young" className="chip chip-accent mono">CY×{p.awards.cy_young}</span>}
                        {p.awards.all_star > 0 && <span title="All-Star" className="chip mono"><Star className="h-2.5 w-2.5" />{p.awards.all_star}</span>}
                      </span>
                    ) : <span className="text-ink-500">—</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FarmPlaceholder({ bref }: { bref: string }) {
  return (
    <div className="card flex items-center gap-3 p-5">
      <div className="grid h-10 w-10 place-items-center rounded-md bg-positive-500/15 text-positive-500">
        <Sprout className="h-5 w-5" />
      </div>
      <div className="flex-1">
        <div className="text-[13px] font-semibold text-ink-100">{bref} farm system · awaiting ingest</div>
        <div className="text-[11px] text-ink-400">MiLB rosters pull (AAA → Rookie) is being built in a parallel worktree. This panel will populate with affiliates, prospects, and ETA proxies once that lands.</div>
      </div>
    </div>
  )
}


function countFarm(farm: import('../data/farm').FarmTeam): number {
  // MiLB-only count — excludes the MLB bucket (those show in the 40-man table)
  const LV: Array<import('../data/farm').FarmLevel> = ['AAA', 'AA', 'A+', 'A', 'R']
  return LV.reduce((a, lv) => a + (farm.levels[lv]?.length ?? 0), 0)
}

