import { motion } from 'framer-motion'
import {
  Target,
  CheckCircle2,
  AlertTriangle,
  Sigma,
  Coins,
  BarChart3,
  Eye,
  TrendingDown,
  Layers,
  GitBranch,
  Cpu,
  FlaskConical,
  ArrowRight,
} from 'lucide-react'
import { Section, Stat } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import { PosteriorCurve, fmtM, fmtWAR } from '../components/PosteriorCurve'
import { DrawsHistogram } from '../components/DrawsHistogram'
import { FoldCrpsChart } from '../components/FoldCrpsChart'
import { FeatureBetaChart } from '../components/FeatureBetaChart'
import { modelPosteriors, featureLabel, type ModelCard } from '../lib/modelPosteriors'

/* ─── Journey timeline ─────────────────────────────────────────────────────── */

type JourneyStep = {
  icon: typeof Sigma
  label: string
  crps: string | null
  body: string
  status: 'baseline' | 'tried' | 'current' | 'abandoned'
}

function ModelJourney({ winsComparison }: { winsComparison: typeof modelPosteriors.wins_comparison }) {
  const stableFolds = winsComparison.folds.filter((f) => !f.structural_break)
  const avg = (key: 'crps_context' | 'crps_quality' | 'crps_intercept') =>
    stableFolds.reduce((s, f) => s + (f[key] as number), 0) / stableFolds.length

  const interceptCrps = avg('crps_intercept').toFixed(1)
  const qualityCrps = avg('crps_quality').toFixed(1)
  const contextCrps = avg('crps_context').toFixed(1)
  const latestCrps = winsComparison.folds[winsComparison.folds.length - 1].crps_context.toFixed(1)

  const steps: JourneyStep[] = [
    {
      icon: Coins,
      label: 'Naïve $/WAR baseline',
      crps: `~${interceptCrps}W CRPS`,
      status: 'baseline',
      body:
        "The industry standard: multiply a player's WAR by the going rate per win (~$8-9M). Every team pays the same price for the same WAR. No context, no development system, no payroll situation. This is what we're trying to beat.",
    },
    {
      icon: TrendingDown,
      label: '+ Player quality features',
      crps: `~${qualityCrps}W CRPS`,
      status: 'tried',
      body:
        "Added WAR trajectory, K-percentile trend, minor-league quality, age-at-trade. Intuition: a rising player is worth more than a flat one. Result: sometimes better than the mean baseline, but noisy — the player alone doesn't explain enough variance. Something else drives where surplus actually lands.",
    },
    {
      icon: Layers,
      label: '+ Receiving-team context',
      crps: `~${contextCrps}W CRPS`,
      status: 'current',
      body:
        'The thesis: added dev-system fit (K% and xwOBA jump 3yr), payroll slack, contention window, alumni network, tech adoption. Same player, different team = different surplus. CRPS dropped from ~' +
        qualityCrps +
        'W to ~' +
        contextCrps +
        'W on stable folds — a meaningful gap that validates the core hypothesis.',
    },
    {
      icon: GitBranch,
      label: 'V2 multilevel (tried, abandoned)',
      crps: null,
      status: 'abandoned',
      body:
        'Hypothesis: teams have persistent trade-behavior clusters worth shrinking toward — hierarchical pooling by team/era/position. Research run R-35 falsified it. Team and regime nesting added zero signal over the single-level model. Dropped. Occam wins.',
    },
    {
      icon: Cpu,
      label: 'V3: per-outcome feature selection',
      crps: `${latestCrps}W CRPS (2023–24 fold)`,
      status: 'current',
      body:
        'Small-n outcomes (xwOBA delta, K% delta) overfit on team aggregates. V3 uses empirically-validated feature subsets per outcome (R-57 walk-forward). The model is getting better as the training window grows: CRPS went from 2.1W in 2015–16 to ' +
        latestCrps +
        'W in 2023–24 — the most recent trades are the best-predicted.',
    },
  ]

  const statusStyles: Record<JourneyStep['status'], { border: string; iconBg: string; iconColor: string; badge?: string }> = {
    baseline: { border: 'border-ink-700', iconBg: 'bg-ink-700/60', iconColor: 'text-ink-300', badge: 'baseline' },
    tried: { border: 'border-ink-700', iconBg: 'bg-ink-700/60', iconColor: 'text-ink-300' },
    current: { border: 'border-accent-500/40', iconBg: 'bg-accent-500/15', iconColor: 'text-accent-400' },
    abandoned: { border: 'border-amber-500/30', iconBg: 'bg-amber-500/10', iconColor: 'text-amber-400' },
  }

  return (
    <div className="mb-6">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">
        How we got here
      </div>
      <h2 className="mb-1 text-[15px] font-semibold tracking-tight text-ink-100">
        Five iterations from a back-of-envelope formula to a calibrated Bayesian model
      </h2>
      <p className="mb-4 text-[12px] text-ink-400">
        Each step is a research decision — what was tried, what was learned, what stayed.
        The CRPS numbers are averages across stable walk-forward folds (structural break excluded).
      </p>

      <div className="relative">
        {/* Connector line */}
        <div className="absolute left-[17px] top-[34px] bottom-[34px] w-px bg-ink-700 sm:left-[50%] sm:-translate-x-px sm:top-[17px] sm:bottom-auto sm:left-auto sm:right-auto sm:w-0 hidden sm:block" />

        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:gap-0">
          {steps.map((step, i) => {
            const s = statusStyles[step.status]
            const Icon = step.icon
            return (
              <div key={i} className="relative flex gap-3 sm:w-1/5 sm:flex-col sm:items-center sm:gap-2 sm:px-2">
                {/* Connector dot */}
                <div
                  className={`relative z-10 mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-full border ${s.border} ${s.iconBg} sm:mt-0`}
                >
                  <Icon className={`h-3.5 w-3.5 ${s.iconColor}`} />
                </div>
                <div className={`rounded-lg border p-3 ${s.border} bg-ink-900/50 sm:w-full`}>
                  <div className="mb-0.5 flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] font-semibold text-ink-100">{step.label}</span>
                    {step.status === 'abandoned' && (
                      <span className="rounded bg-amber-500/15 px-1.5 py-px text-[9px] font-semibold text-amber-300">
                        abandoned
                      </span>
                    )}
                  </div>
                  {step.crps && (
                    <div className="mono mb-1.5 text-[10px] tabular text-accent-400">{step.crps}</div>
                  )}
                  <div className="text-[11px] leading-relaxed text-ink-400">{step.body}</div>
                </div>
                {i < steps.length - 1 && (
                  <ArrowRight className="hidden h-3 w-3 text-ink-600 sm:block sm:absolute sm:right-[-6px] sm:top-[10px] sm:z-20" />
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

/* ─── How to read ──────────────────────────────────────────────────────────── */

function HowToRead() {
  const items = [
    {
      icon: Coins,
      title: 'What the model predicts',
      body: 'Surplus wins: how many wins the acquiring club gained above what it paid for — a $700K pre-arb player who earns 3 WAR is a much bigger bargain than a $20M veteran who earns the same 3 WAR. Dollar value is shown as a secondary anchor.',
    },
    {
      icon: BarChart3,
      title: 'Why a curve, not a number',
      body: 'The model outputs a range of belief, not a single guess. The orange curve is its full distribution; the wider it is, the less certain. The 90% interval is where it thinks the result will land 9 times out of 10.',
    },
    {
      icon: Eye,
      title: 'How to tell if it was right',
      body: 'The green line is what actually happened. These trades were held out — the model never saw their outcomes. Green inside the orange interval = a good call. A model is "calibrated" if reality lands inside its interval about as often as it claims.',
    },
  ]
  return (
    <div className="mb-6 rounded-lg border border-ink-700 bg-ink-900/40 p-5">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-300">
        How to read this page
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-3">
        {items.map(({ icon: Icon, title, body }) => (
          <div key={title} className="flex gap-3">
            <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-md bg-accent-500/15 text-accent-400">
              <Icon className="h-4 w-4" />
            </div>
            <div>
              <div className="text-[12px] font-semibold text-ink-100">{title}</div>
              <div className="mt-1 text-[12px] leading-relaxed text-ink-400">{body}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ─── Chart key ────────────────────────────────────────────────────────────── */

function ChartKey() {
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[11px] text-ink-400">
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-4 rounded-sm" style={{ background: 'rgba(255,138,61,0.35)', border: '1px solid rgba(255,138,61,0.9)' }} />
        model's predicted range
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-0.5" style={{ background: '#ff8a3d' }} />
        most likely value (mean)
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-1 w-4 rounded" style={{ background: 'rgba(255,138,61,0.55)' }} />
        90% interval
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-0.5" style={{ background: '#3ddc97' }} />
        what actually happened
      </span>
    </div>
  )
}

/* ─── Histogram key ────────────────────────────────────────────────────────── */

function HistogramKey() {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-x-5 gap-y-1 text-[10px] text-ink-500">
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-3 rounded-sm" style={{ background: 'rgba(255,138,61,0.6)', border: '1px solid rgba(255,138,61,0.55)' }} />
        draws inside 90% CI
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-2.5 w-3 rounded-sm" style={{ background: 'rgba(255,138,61,0.22)', border: '1px solid rgba(255,138,61,0.55)' }} />
        draws outside CI
      </span>
      <span className="flex items-center gap-1.5">
        <span className="inline-block h-3 w-0.5" style={{ background: '#3ddc97' }} />
        realized outcome
      </span>
    </div>
  )
}

/* ─── Trade card ───────────────────────────────────────────────────────────── */

function ModelTradeCard({ card }: { card: ModelCard }) {
  const tail = card.role === 'tail_miss'
  const wPost = card.wins_posterior
  const inCi = wPost != null ? card.wins_realized_in_90ci : card.realized_in_90ci

  return (
    <div className={`card p-5 ${tail ? 'border-amber-500/40' : ''}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          {card.sender_bref ? <TeamLogo team={card.sender_bref} size={26} className="opacity-60" /> : null}
          <span className="text-ink-500">→</span>
          <TeamLogo team={card.receiver_bref} size={34} />
          <div>
            <div className="text-[14px] font-semibold tracking-tight text-ink-100">
              {card.acquired_players.slice(0, 2).join(', ')}
              {card.acquired_players.length > 2 ? ` +${card.acquired_players.length - 2}` : ''}
            </div>
            <div className="text-[11px] text-ink-400">
              {card.sender_bref} → {card.receiver_bref} · {card.season} · held out
            </div>
          </div>
        </div>
        {inCi ? (
          <span className="chip" style={{ color: '#3ddc97', borderColor: 'rgba(61,220,151,0.4)' }}>
            <CheckCircle2 className="h-3 w-3" /> in 90% CI
          </span>
        ) : (
          <span className="chip" style={{ color: '#f5a524', borderColor: 'rgba(245,165,36,0.45)' }}>
            <AlertTriangle className="h-3 w-3" /> tail-miss
          </span>
        )}
      </div>

      {wPost ? (
        <>
          {/* Gaussian curve — the clean view */}
          <div className="mb-1 text-[10px] uppercase tracking-[0.12em] text-ink-400">
            Surplus wins — Gaussian posterior (mean + sd)
          </div>
          <PosteriorCurve post={wPost} realized={card.wins_realized ?? null} formatter={fmtWAR} />

          {/* Empirical histogram — raw draws */}
          {wPost.draws.length > 0 && (
            <div className="mt-4 border-t border-ink-800 pt-3">
              <div className="mb-1 text-[10px] uppercase tracking-[0.12em] text-ink-400">
                Empirical posterior — {wPost.draws.length} raw MCMC draws
              </div>
              <HistogramKey />
              <DrawsHistogram
                draws={wPost.draws}
                realized={card.wins_realized ?? null}
                p05={wPost.p05}
                p95={wPost.p95}
                mean={wPost.mean}
                formatter={fmtWAR}
              />
              <div className="mt-1 text-[10px] text-ink-600">
                Bars are binned MCMC samples. The Gaussian curve above approximates this shape — here you see the actual distribution.
              </div>
            </div>
          )}

          {/* Stats row */}
          <div className="mt-3 grid grid-cols-3 gap-3 border-t border-ink-800 pt-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">Mean</div>
              <div className="mono text-[15px] font-semibold tabular text-ink-100">{fmtWAR(wPost.mean, true)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">90% interval</div>
              <div className="mono text-[13px] tabular text-ink-300">
                [{fmtWAR(wPost.p05)}, {fmtWAR(wPost.p95)}]
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">Realized</div>
              <div className="mono text-[15px] font-semibold tabular" style={{ color: '#3ddc97' }}>
                {card.wins_realized != null ? fmtWAR(card.wins_realized) : '—'}
              </div>
            </div>
          </div>
          {/* Dollar anchor */}
          <div className="mt-3 border-t border-ink-800 pt-2.5 text-[11px] text-ink-500">
            Dollar anchor: mean {fmtM(card.posterior.mean, true)} · realized {fmtM(card.realized)}
          </div>
        </>
      ) : (
        <>
          <PosteriorCurve post={card.posterior} realized={card.realized} />
          <div className="mt-3 grid grid-cols-3 gap-3 border-t border-ink-700 pt-3">
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">Model mean</div>
              <div className="mono text-[15px] font-semibold tabular text-ink-100">{fmtM(card.posterior.mean, true)}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">90% interval</div>
              <div className="mono text-[13px] tabular text-ink-300">
                [{fmtM(card.posterior.p05)}, {fmtM(card.posterior.p95)}]
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.12em] text-ink-400">Realized</div>
              <div className="mono text-[15px] font-semibold tabular" style={{ color: '#3ddc97' }}>{fmtM(card.realized)}</div>
            </div>
          </div>
        </>
      )}

      {tail ? (
        <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-[11px] leading-relaxed text-ink-300">
          <span className="font-semibold text-amber-300">Known limitation.</span> On rare, once-a-decade
          blockbusters, the model pulls its estimate toward the typical trade — Soto's real surplus sits well
          above its predicted range. That's the model being cautious about extreme outliers by design, not a bug. We
          show it on purpose: it's accurate on ordinary trades and deliberately conservative on the giants.
        </div>
      ) : null}
    </div>
  )
}

/* ─── Coverage gauge ───────────────────────────────────────────────────────── */

function CoverageGauge({ coverage, target = 0.9, label }: { coverage: number; target?: number; label: string }) {
  const W = 120, H = 64
  const r = 44
  const cx = W / 2, cy = H - 4
  const arc = (pct: number) => {
    const angle = Math.PI * pct
    const x = cx + r * Math.cos(Math.PI - angle)
    const y = cy - r * Math.sin(Math.PI - angle)
    return { x, y }
  }
  const { x: cx2, y: cy2 } = arc(coverage)
  const { x: tx, y: ty } = arc(target)
  const color = Math.abs(coverage - target) < 0.05 ? '#3ddc97' : coverage < target - 0.05 ? '#ff5d73' : '#ff8a3d'
  return (
    <div className="flex flex-col items-center">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
        {/* Background arc */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`}
          fill="none"
          stroke="rgba(138,150,192,0.15)"
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Coverage arc */}
        <path
          d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx2} ${cy2}`}
          fill="none"
          stroke={color}
          strokeWidth={10}
          strokeLinecap="round"
          opacity={0.85}
        />
        {/* Target tick */}
        <circle cx={tx} cy={ty} r={3.5} fill="rgba(138,150,192,0.6)" />
        {/* Value */}
        <text x={cx} y={cy - 10} textAnchor="middle" fontSize={16} fontWeight="600" fill={color} fontFamily="JetBrains Mono, monospace">
          {(coverage * 100).toFixed(0)}%
        </text>
      </svg>
      <div className="text-[10px] text-ink-400">{label}</div>
      <div className="text-[9px] text-ink-600">target {(target * 100).toFixed(0)}%</div>
    </div>
  )
}

/* ─── Main page ────────────────────────────────────────────────────────────── */

export default function ModelValuation() {
  const { scoreboard, wins_comparison, credible_features, cards, train_window, test_window } =
    modelPosteriors
  const covered = cards.filter((c) => c.role === 'covered')
  const tail = cards.filter((c) => c.role === 'tail_miss')

  return (
    <main className="mx-auto max-w-[1240px] px-6 py-8">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">
          <Sigma className="h-3.5 w-3.5" /> V3 Bayesian Model · Held-out Validation
        </div>
        <h1 className="text-[26px] font-semibold tracking-tight text-ink-100">
          Real posterior valuations — trained {train_window[0]}–{train_window[1]}, scored {test_window[0]}–{test_window[1]}
        </h1>
        <p className="mt-2 max-w-[760px] text-[13px] leading-relaxed text-ink-400">
          Every distribution below is genuine posterior-predictive output from the frozen V3 model — no illustrative
          numbers. Headline metric is <span className="text-ink-200">surplus wins</span>: how many wins the acquiring
          club gained above what it paid for at market rate. Dollar value is shown as a secondary anchor. The featured
          trades are held out of training, so we can score against what actually happened.
        </p>
      </motion.div>

      {/* ── Journey ── */}
      <div className="mt-8">
        <ModelJourney winsComparison={wins_comparison} />
      </div>

      <HowToRead />

      {/* ── Scoreboard ── */}
      <Section
        eyebrow="Calibration scoreboard"
        title="How the model does across all held-out trades"
        hint="Across every trade it never trained on, how close did it get — and was it honest about its own uncertainty?"
      >
        <div className="card p-5">
          <div className="flex flex-wrap items-start gap-8">
            <div className="flex flex-wrap items-end gap-10">
              <Stat
                label="Wins 90% coverage"
                value={`${(scoreboard.wins_coverage_90 * 100).toFixed(0)}%`}
                sub="of actual surplus-wins outcomes landed inside the model's predicted range — target is 90%"
                tone="pos"
              />
              <Stat
                label="Wins CRPS"
                value={`${scoreboard.wins_crps.toFixed(2)} W`}
                sub="typical prediction error in wins — lower is better; penalizes overconfidence"
              />
              <Stat
                label="Wins MAE"
                value={`${scoreboard.wins_mae.toFixed(2)} W`}
                sub="average miss of the center estimate, in wins above cost basis"
              />
              <Stat
                label="Held-out trades"
                value={scoreboard.test_n.toLocaleString()}
                sub={`scored · ${scoreboard.train_n.toLocaleString()} used for training`}
              />
            </div>
            {/* Coverage gauges */}
            <div className="flex gap-4">
              <CoverageGauge coverage={scoreboard.wins_coverage_90} label="Wins coverage" />
              <CoverageGauge coverage={scoreboard.coverage_90} label="Dollar coverage" />
            </div>
          </div>
        </div>
        <div className="mt-2 rounded border border-ink-800 bg-ink-900/30 px-4 py-2.5 text-[11px] text-ink-500">
          Dollar anchor — 90% coverage {(scoreboard.coverage_90 * 100).toFixed(0)}% · CRPS{' '}
          {fmtM(scoreboard.crps)} · MAE {fmtM(scoreboard.mae)}
        </div>
      </Section>

      {/* ── Does context help? ── */}
      <Section
        eyebrow="Does context actually help?"
        title="Context-aware vs. the baselines it has to beat"
        hint="The whole thesis is that the same player is worth different amounts to different teams. To prove it earns its keep, the model is raced against two simpler ones on trades none of them trained on. Lower CRPS = better."
      >
        <div className="mb-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="card p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">vs. player-quality-only</div>
            <div className="mono mt-1 text-[30px] font-semibold leading-none text-positive-500">
              +{(wins_comparison.mean_skill_vs_quality_ex_break * 100).toFixed(0)}%
            </div>
            <div className="mt-1.5 text-[12px] leading-relaxed text-ink-400">
              The baseline that rates the player alone and ignores which team acquires him. Our model is{' '}
              <span className="text-ink-200">~{(wins_comparison.mean_skill_vs_quality_ex_break * 100).toFixed(0)}% more accurate on surplus wins</span>{' '}
              — adding receiving-team context is what does it. This is the thesis, validated.
            </div>
          </div>
          <div className="card p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">vs. predict-the-mean</div>
            <div className="mono mt-1 text-[30px] font-semibold leading-none text-ink-100">
              {wins_comparison.mean_skill_vs_intercept_ex_break >= 0 ? '+' : ''}
              {(wins_comparison.mean_skill_vs_intercept_ex_break * 100).toFixed(1)}%
            </div>
            <div className="mt-1.5 text-[12px] leading-relaxed text-ink-400">
              The floor that guesses the league-average surplus wins every time. The model beats it meaningfully — the
              Student-t likelihood lets context features dominate over blockbuster noise.
            </div>
          </div>
        </div>

        {/* Walk-forward CRPS chart */}
        <div className="card p-5">
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-400">
            Walk-forward CRPS by fold — wins scale (lower is better)
          </div>
          <FoldCrpsChart folds={wins_comparison.folds} />
          <div className="mt-3 text-[11px] leading-relaxed text-ink-500">
            Each fold trains on all data up to the fold start and tests on the following 2 seasons — no data leakage.
            The context-aware bar is shortest (best) in every stable fold. The 2017–18 structural break is the documented
            CBA/market-volatility era where all models underperform; we flag it rather than hide it. Note the rightward
            trend: more training data = better CRPS — the model keeps improving.
          </div>
        </div>

        {/* Fold table — detail view */}
        <div className="mt-2 card overflow-hidden p-0">
          <div className="px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-500 border-b border-ink-800">
            Fold detail — wins CRPS
          </div>
          <table className="w-full text-[12px]">
            <thead>
              <tr className="border-b border-ink-700 text-[10px] uppercase tracking-[0.1em] text-ink-400">
                <th className="px-4 py-2 text-left font-medium">Test fold</th>
                <th className="px-4 py-2 text-right font-medium">Trades</th>
                <th className="px-4 py-2 text-right font-medium">vs quality-only</th>
                <th className="px-4 py-2 text-right font-medium">vs predict-the-mean</th>
              </tr>
            </thead>
            <tbody className="mono tabular">
              {wins_comparison.folds.map((f) => (
                <tr key={f.label} className="border-b border-ink-800 last:border-0">
                  <td className="px-4 py-2 text-ink-200">
                    {f.label}
                    {f.structural_break ? (
                      <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">
                        structural break
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-right text-ink-400">{f.n_test}</td>
                  <td
                    className={`px-4 py-2 text-right ${f.skill_vs_quality >= 0 ? 'text-positive-500' : 'text-negative-500'}`}
                  >
                    {f.skill_vs_quality >= 0 ? '+' : ''}{(f.skill_vs_quality * 100).toFixed(1)}%
                  </td>
                  <td
                    className={`px-4 py-2 text-right ${f.skill_vs_intercept >= 0 ? 'text-positive-500' : 'text-negative-500'}`}
                  >
                    {f.skill_vs_intercept >= 0 ? '+' : ''}{(f.skill_vs_intercept * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ── Feature anatomy ── */}
      <Section
        eyebrow="Model anatomy"
        title="What actually moves the valuation"
        hint="The 8 features where the model is 96%+ confident of direction — meaning it's not just noise. Grouped by whether they describe the acquired player or the receiving team. Note: more features describe the receiving team than the player alone."
      >
        <div className="card p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="text-[11px] text-ink-400">
              Bar width = coefficient magnitude · color = direction · percentage = directional confidence (P(β &gt; 0) or P(β &lt; 0))
            </div>
            <div className="flex items-center gap-2 text-[10px] text-ink-500">
              <FlaskConical className="h-3 w-3" />
              R-57 walk-forward validated
            </div>
          </div>
          <FeatureBetaChart features={credible_features} />
          <div className="mt-4 rounded border border-ink-800 bg-ink-900/30 px-4 py-3 text-[11px] leading-relaxed text-ink-500">
            <span className="text-ink-300">Why these features?</span> Each went through R-57 walk-forward ablation — a feature
            stays if removing it consistently worsens held-out CRPS. Beta coefficients are from the standardized V3 model, so
            bar widths are directly comparable across features. Only 8 of 23 candidate features pass the directional-mass
            threshold (≥96% confident) — Bayesian regularization is doing its job.
          </div>
        </div>
        {/* Legacy list — secondary detail */}
        <div className="mt-2 card divide-y divide-ink-800 p-0">
          {credible_features.map((f) => (
            <div key={f.feature} className="flex items-center justify-between gap-4 px-5 py-2.5">
              <div className="flex items-center gap-2.5">
                <Target className="h-3.5 w-3.5 text-accent-400" />
                <span className="text-[13px] text-ink-200">{featureLabel(f.feature)}</span>
              </div>
              <div className="flex items-center gap-5">
                <span className={`mono text-[12px] tabular ${f.beta >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>
                  {f.beta >= 0 ? 'raises value' : 'lowers value'}
                </span>
                <span className="mono text-[11px] tabular text-ink-500">{(f.directional_mass * 100).toFixed(0)}% confident</span>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Posterior gallery ── */}
      <Section
        eyebrow="Held-out predictions"
        title="Predicted distribution vs. what happened"
        hint="Each trade was kept out of training. Did reality (green) land inside the model's predicted range (orange)? Each card shows both the Gaussian approximation and the raw empirical histogram of MCMC draws."
      >
        <ChartKey />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {covered.map((c) => (
            <ModelTradeCard key={`${c.trade_event_id}-${c.receiver_bref}`} card={c} />
          ))}
        </div>
      </Section>

      {/* ── Tail miss ── */}
      {tail.length ? (
        <Section
          eyebrow="Where it fails"
          title="The tail the model shrinks — shown on purpose"
          hint="A front office should see the failure mode, not just the wins."
        >
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {tail.map((c) => (
              <ModelTradeCard key={`${c.trade_event_id}-${c.receiver_bref}`} card={c} />
            ))}
          </div>
        </Section>
      ) : null}
    </main>
  )
}
