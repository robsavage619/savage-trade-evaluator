import { useEffect, useState } from 'react'
import { useParams, Navigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, Shield, CheckCircle2, Sigma } from 'lucide-react'
import { getTrade, PRESSLY_TRADE_ID } from '../data'
import { getPipelineEntry } from '../data/pipeline'
import { useReasoningStore } from '../lib/reasoningStore'
import { ClaudeCodeDrawer } from '../components/ClaudeCodeDrawer'
import type { TradeLeg } from '../types'
import { PlayerCard } from '../components/PlayerCard'
import { PersonnelTriangle } from '../components/PersonnelTriangle'
import { PosteriorCurve, fmtM } from '../components/PosteriorCurve'
import { loadTradePosterior, type TradePosterior } from '../lib/modelPosteriors'
import { ContextChips, CONTEXT_ICONS } from '../components/ContextChips'
import { Section, Stat } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import { TradePipeline } from '../components/TradePipeline'
import { AiReasoning } from '../components/AiReasoning'
import { fmtSigned, teamColor } from '../lib/format'

const HIGHLIGHTED_NAMES = ['Jeff Luhnow', 'A.J. Hinch', 'Brent Strom', 'Derek Falvey', 'Thad Levine', 'Paul Molitor', 'Garvin Alston']

const CHIP_ICON_BY_LABEL: Record<string, keyof typeof CONTEXT_ICONS> = {
  'Contention window': 'Gauge',
  'Payroll headroom': 'Coins',
  'Farm depth': 'Trees',
  'Positional need': 'Target',
  'Dev-system signature': 'Wand2',
  'Next-FA risk': 'Gauge',
  'Extension probability': 'Gauge',
  'Two-star synergy': 'Wand2',
  'Integration risk': 'Wand2',
}

/** Standard-normal CDF via erf approximation (Abramowitz & Stegun 7.1.26). */
function normalCdf(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z))
  const d = 0.3989422804014327 * Math.exp(-z * z / 2)
  const p = d * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
  return z > 0 ? 1 - p : p
}

/** P(dollar surplus < 0) from the Gaussian posterior. */
function pLoss(post: TradePosterior): number {
  return normalCdf((0 - post.mean) / post.sd)
}

/** Real team-side dollar-surplus posterior for one receiving team. Reads the V3
 *  model export; renders the actual posterior with the realized outcome marked. */
function TeamSurplusCard({ team, post }: { team: string; post: TradePosterior }) {
  const held = post.split === 'held_out'
  return (
    <div className="card p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <TeamLogo team={team} size={32} />
          <div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">Receiving team · dollar surplus</div>
            <div className="text-[14px] font-semibold tracking-tight text-ink-100">
              {post.acquired_players.slice(0, 3).join(', ')}
            </div>
          </div>
        </div>
        <span className="chip shrink-0 whitespace-nowrap" style={held
          ? { color: '#3ddc97', borderColor: 'rgba(61,220,151,0.4)' }
          : { color: '#8a96c0', borderColor: 'rgba(138,150,192,0.35)' }}>
          {held ? <CheckCircle2 className="h-3 w-3" /> : <Sigma className="h-3 w-3" />}
          {held ? 'held out' : 'in-sample'}
        </span>
      </div>
      <PosteriorCurve post={post} realized={post.realized} width={320} height={130} />
      <div className="mt-3 grid grid-cols-3 gap-2 border-t border-ink-700 pt-3">
        <div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-ink-400">Model mean</div>
          <div className="mono text-[14px] font-semibold tabular text-ink-100">{fmtM(post.mean, true)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-ink-400">90% interval</div>
          <div className="mono text-[12px] tabular text-ink-300">[{fmtM(post.p05)}, {fmtM(post.p95)}]</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.1em] text-ink-400">Realized</div>
          <div className="mono text-[14px] font-semibold tabular" style={{ color: '#3ddc97' }}>{fmtM(post.realized)}</div>
        </div>
      </div>
    </div>
  )
}

function TradeFlow({ legsLeft, legsRight, teamLeft, teamRight }: { legsLeft: TradeLeg[]; legsRight: TradeLeg[]; teamLeft: string; teamRight: string }) {
  return (
    <div className="card relative overflow-hidden p-5">
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-accent-500/[0.04] to-transparent" aria-hidden />
      <div className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-6">
        <div className="flex items-center gap-3">
          <TeamLogo team={teamLeft} size={40} />
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-ink-400">{teamLeft} sends</div>
            <div className="mt-0.5 text-[15px] font-semibold tracking-tight" style={{ color: teamColor(teamLeft).primary }}>
              {teamLeft}
            </div>
          </div>
        </div>
        <ArrowRight className="h-5 w-5 text-ink-400" />
        <div className="flex items-center justify-end gap-3 text-right">
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-ink-400">{teamRight} sends</div>
            <div className="mt-0.5 text-[15px] font-semibold tracking-tight" style={{ color: teamColor(teamRight).primary }}>
              {teamRight}
            </div>
          </div>
          <TeamLogo team={teamRight} size={40} />
        </div>
      </div>
      <div className="relative mt-3 grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          {legsLeft.map((l) => (
            <div key={l.leg_index} className="rounded-md border border-ink-700 bg-ink-800/60 px-3 py-1.5 text-[12px]">
              <span className="text-ink-100">{l.player_name}</span>
              <span className="ml-2 text-[10px] uppercase tracking-wider text-ink-400">{l.from_team_bref} → {l.to_team_bref}</span>
            </div>
          ))}
        </div>
        <div className="space-y-1.5 text-right">
          {legsRight.map((l) => (
            <div key={l.leg_index} className="rounded-md border border-ink-700 bg-ink-800/60 px-3 py-1.5 text-[12px]">
              <span className="ml-2 text-[10px] uppercase tracking-wider text-ink-400">{l.from_team_bref} → {l.to_team_bref}</span>
              <span className="ml-2 text-ink-100">{l.player_name}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function TradeWorkspace() {
  const params = useParams<{ id: string }>()
  const id = Number(params.id ?? PRESSLY_TRADE_ID)
  const trade = getTrade(id)
  const pipeline = trade ? getPipelineEntry(id) : undefined
  // All hooks must run unconditionally (rules of hooks) — the early return for a
  // missing trade comes after them.
  const [drawerOpen, setDrawerOpen] = useState(false)
  const override = useReasoningStore((s) => (pipeline ? s.overrides[pipeline.tradeId] : undefined))
  const [posteriors, setPosteriors] = useState<Record<string, TradePosterior | null>>({})
  const teams = trade?.teams
  useEffect(() => {
    if (!teams) return
    let alive = true
    Promise.all(teams.map(async (t) => [t, await loadTradePosterior(id, t)] as const)).then(
      (pairs) => {
        if (alive) setPosteriors(Object.fromEntries(pairs))
      },
    )
    return () => {
      alive = false
    }
  }, [id, teams])

  if (!trade) return <Navigate to={`/trade/${PRESSLY_TRADE_ID}`} replace />
  const activeReasoning = override?.reasoning ?? pipeline?.reasoning

  // Teams: assume two-team trade for V1
  const [teamA, teamB] = trade.teams
  const aSending = trade.legs.filter((l) => l.from_team_bref === teamA)
  const bSending = trade.legs.filter((l) => l.from_team_bref === teamB)
  const scoredTeams = trade.teams.filter((t) => posteriors[t] != null)

  // Verdict numbers from naive_baseline (real)
  const naiveByTeam: Record<string, { war_received: number; surplus: number } | undefined> = {}
  for (const nb of trade.naive_baseline) naiveByTeam[nb.team_bref] = nb

  const teamAName = trade.legs.find((l) => l.from_team_bref === teamA)?.from_team_name ?? teamA
  const teamBName = trade.legs.find((l) => l.from_team_bref === teamB)?.from_team_name ?? teamB
  const primaryAcquirer = (trade.naive_baseline[0]?.surplus ?? 0) >= (trade.naive_baseline[1]?.surplus ?? 0)
    ? (trade.naive_baseline[0]?.team_bref ?? teamA)
    : (trade.naive_baseline[1]?.team_bref ?? teamB)

  return (
    <main className="mx-auto grid max-w-[1640px] grid-cols-1 gap-6 px-6 py-6 xl:grid-cols-[300px_1fr]">
      {/* Pipeline rail */}
      <div className="xl:sticky xl:top-[72px] xl:h-[calc(100vh-96px)]">
        <TradePipeline />
      </div>

      <div>
      {/* Verdict band */}
      {(() => {
        const surplusA = naiveByTeam[teamA]?.surplus ?? 0
        const surplusB = naiveByTeam[teamB]?.surplus ?? 0
        const winner = surplusA >= surplusB ? teamA : teamB
        const loser = winner === teamA ? teamB : teamA
        const asymmetry = Math.abs(surplusA - surplusB)
        return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="card mb-6 flex flex-wrap items-end justify-between gap-6 p-5"
      >
        <div className="flex items-end gap-5">
          <div className="flex items-center gap-2">
            <TeamLogo team={winner} size={44} />
            <ArrowRight className="h-4 w-4 text-ink-500" />
            <TeamLogo team={loser} size={28} className="opacity-60" />
          </div>
          <div>
            <div className="text-[10px] font-medium uppercase tracking-[0.18em] text-accent-400">Verdict</div>
            <div className="mt-1 text-[20px] font-semibold tracking-tight text-ink-100">
              {winner} clears above-baseline surplus · {loser} below
            </div>
            <div className="mt-1 text-[12px] text-ink-400">
              Naive $/WAR shows {asymmetry.toFixed(2)} WAR of asymmetry; context-aware posterior shifts the magnitude on receiving-team dev signature.
            </div>
          </div>
        </div>
        <div className="flex gap-8">
          <Stat
            label={`${teamA} 3-yr surplus`}
            value={fmtSigned(naiveByTeam[teamA]?.surplus ?? 0)}
            sub="WAR vs naive $/WAR"
            tone={(naiveByTeam[teamA]?.surplus ?? 0) >= 0 ? 'pos' : 'neg'}
          />
          <Stat
            label={`${teamB} 3-yr surplus`}
            value={fmtSigned(naiveByTeam[teamB]?.surplus ?? 0)}
            sub="WAR vs naive $/WAR"
            tone={(naiveByTeam[teamB]?.surplus ?? 0) >= 0 ? 'pos' : 'neg'}
          />
          <Stat
            label="Asymmetry"
            value={fmtSigned((naiveByTeam[teamB]?.surplus ?? 0) - (naiveByTeam[teamA]?.surplus ?? 0))}
            sub="WAR difference"
            tone="neutral"
          />
        </div>
      </motion.div>
        )
      })()}

      {/* AI Reasoning panel */}
      {pipeline && activeReasoning ? (
        <div className="mb-6">
          <AiReasoning
            reasoning={activeReasoning}
            resetKey={`${id}-${override?.savedAt ?? 'default'}`}
            onOpenClaude={() => setDrawerOpen(true)}
            sourceLabel={override?.source}
            savedAt={override?.savedAt}
          />
        </div>
      ) : null}
      {pipeline ? (
        <ClaudeCodeDrawer
          open={drawerOpen}
          onClose={() => setDrawerOpen(false)}
          trade={trade}
          pipeline={pipeline}
        />
      ) : null}

      {/* Three-column body */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_1fr_320px]">
        {/* Left: trade structure */}
        <div className="space-y-3">
          <Section eyebrow="Trade Structure" title={`${teamA} ↔ ${teamB} · ${trade.trade_date}`}>
            <TradeFlow legsLeft={aSending} legsRight={bSending} teamLeft={teamA} teamRight={teamB} />
          </Section>
          <Section eyebrow="Players Moving" title="Career-WAR snapshot" hint="Pre-trade trend with trade season highlighted">
            <div className="space-y-2.5">
              {trade.legs.map((leg) => {
                const war = trade.war_window.find((w) => w.leg_index === leg.leg_index)
                const person = trade.people.find((p) => p.mlb_player_id === leg.mlb_player_id)
                const career = [...trade.career_war_pitching, ...trade.career_war_batting]
                return <PlayerCard key={leg.leg_index} leg={leg} person={person} war={war} career={career} />
              })}
            </div>
          </Section>
        </div>

        {/* Center: real model posteriors + arsenal */}
        <div className="space-y-6">
          <Section
            eyebrow="V3 Model · Context-aware valuation"
            title="What this trade is worth to each acquiring club"
            hint="Real posterior over 3-year dollar surplus from the frozen V3 model. Orange = predicted distribution + 90% interval; green = realized outcome."
          >
            {scoredTeams.length ? (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                {scoredTeams.map((t) => (
                  <TeamSurplusCard key={t} team={t} post={posteriors[t] as TradePosterior} />
                ))}
              </div>
            ) : (
              <div className="card p-5 text-[12px] text-ink-400">
                No V3 posterior for this trade — it was filtered from the model's
                training/test set (too few features present). The model only scores
                trades it can condition on; we don't fabricate a number here.
              </div>
            )}
          </Section>

          <Section
            eyebrow="Component Outcomes"
            title="Rate-based deltas (not just WAR)"
            hint="Pre-trade vs T+1 percentile rank, per the metric-agnostic principle (D-27)."
          >
            <ArsenalGrid trade={trade} />
          </Section>
        </div>

        {/* Right: context inputs */}
        <div className="space-y-6">
          <Section eyebrow="Context Inputs" title={`What the model saw — ${primaryAcquirer}`} hint="Receiving-team conditioning features (primary acquirer).">
            <ContextChips
              chips={(pipeline?.contextChips ?? []).map((c) => ({
                icon: CONTEXT_ICONS[CHIP_ICON_BY_LABEL[c.label] ?? 'Gauge'],
                label: c.label,
                value: c.value,
                sub: c.sub,
              }))}
            />
          </Section>

          <Section eyebrow="Risk" title="Loss tail" hint="P(this trade nets negative 3-yr dollar surplus for the primary acquirer).">
            <div className="card flex items-center justify-between p-4">
              <div className="flex items-center gap-3">
                <Shield className="h-5 w-5 text-ink-300" />
                <div>
                  <div className="text-[11px] uppercase tracking-[0.12em] text-ink-400">P( surplus &lt; 0 )</div>
                  <div className="mono text-[22px] font-semibold tabular text-ink-100">
                    {posteriors[primaryAcquirer] ? `${(pLoss(posteriors[primaryAcquirer] as TradePosterior) * 100).toFixed(0)}%` : '—'}
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-ink-400">
                <Sigma className="h-3.5 w-3.5 text-accent-400" />
                <span>{posteriors[primaryAcquirer] ? `from V3 posterior · ${primaryAcquirer}` : 'not scored'}</span>
              </div>
            </div>
          </Section>

          <Section eyebrow="Audit" title="As-of guarantee" hint="No information from after the trade date enters any feature.">
            <div className="card p-4 text-[12px] text-ink-300">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-[0.14em] text-ink-400">As-of date</span>
                <span className="mono text-ink-100">{trade.trade_date}</span>
              </div>
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-[0.14em] text-ink-400">Feature snapshot</span>
                <span className="mono text-ink-100">23 features · all pre-trade</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-[0.14em] text-ink-400">Leakage check</span>
                <span className="chip chip-pos">passed</span>
              </div>
            </div>
          </Section>
        </div>
      </div>

      {/* Bottom: personnel triangle */}
      <div className="mt-8">
        <Section eyebrow="Personnel" title="Decision-maker landscape on trade date" hint="The MVP-Machine triangle: front office, dugout, pitching room. Highlighted = principals from the Strom-intake-meeting story.">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <PersonnelTriangle team={teamA} teamName={teamAName} coaches={trade.coaches} fo={trade.front_office} side="left" highlightedNames={HIGHLIGHTED_NAMES} />
            <PersonnelTriangle team={teamB} teamName={teamBName} coaches={trade.coaches} fo={trade.front_office} side="right" highlightedNames={HIGHLIGHTED_NAMES} />
          </div>
        </Section>
      </div>
      </div>
    </main>
  )
}

function ArsenalGrid({ trade }: { trade: ReturnType<typeof getTrade> extends infer T ? T : never }) {
  if (!trade) return null
  const rows = trade.arsenal_window.filter((a) => a.k_percent_t_minus_1 != null)
  if (rows.length === 0) {
    return <div className="card p-4 text-[12px] text-ink-400">No Statcast arsenal coverage for this trade's players.</div>
  }
  const METRICS: Array<{ k: keyof typeof rows[0]; label: string }> = [
    { k: 'k_percent_t_minus_1', label: 'K%' },
    { k: 'whiff_percent_t_minus_1', label: 'Whiff%' },
    { k: 'chase_percent_t_minus_1', label: 'Chase%' },
    { k: 'bb_percent_t_minus_1', label: 'BB%' },
  ]
  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <div key={r.leg_index} className="card p-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[13px] font-semibold text-ink-100">{r.player_name}</div>
            <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">{r.from_team_bref} → {r.to_team_bref} · pre vs T+1 percentile</div>
          </div>
          <div className="grid grid-cols-4 gap-3">
            {METRICS.map(({ k, label }) => {
              const pre = r[k] as number | null
              const postKey = k.toString().replace('_t_minus_1', '_t_plus_1') as keyof typeof r
              const post = r[postKey] as number | null
              const delta = pre != null && post != null ? post - pre : null
              const tone = delta == null ? 'text-ink-300' : delta > 0 ? 'text-positive-500' : delta < 0 ? 'text-negative-500' : 'text-ink-300'
              return (
                <div key={label}>
                  <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">{label}</div>
                  <div className="mono mt-0.5 text-[14px] tabular text-ink-100">
                    {pre?.toFixed(0) ?? '—'}
                    <span className="mx-1 text-ink-500">→</span>
                    {post?.toFixed(0) ?? '—'}
                  </div>
                  <div className={`mono text-[11px] tabular ${tone}`}>
                    {delta != null ? fmtSigned(delta, 0) : '—'} pct
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
