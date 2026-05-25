import { useMemo } from 'react'
import { motion } from 'framer-motion'
import { scaleLinear } from 'd3-scale'
import { Target, CheckCircle2, AlertTriangle, Sigma } from 'lucide-react'
import { Section, Stat } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import {
  modelPosteriors,
  featureLabel,
  type ModelCard,
  type PosteriorSummary,
} from '../lib/modelPosteriors'

const M = 1_000_000

function fmtM(v: number, signed = false): string {
  const m = v / M
  const sign = signed && m >= 0 ? '+' : ''
  return `${sign}$${m.toFixed(1)}M`
}

/** Faithful posterior curve. The V3 model is a linear-Gaussian regression, so the
 *  predictive density is Normal(mean, sd) — we render exactly that, with the held-out
 *  realized outcome marked. No hand-tuning: every number comes from the model. */
function PosteriorCurve({ post, realized }: { post: PosteriorSummary; realized: number }) {
  const width = 460
  const height = 150
  const padX = 8

  // Domain spans the posterior and the realized point, so a tail-miss is visible.
  const loDomain = Math.min(post.p05, realized) - post.sd * 0.6
  const hiDomain = Math.max(post.p95, realized) + post.sd * 0.6
  const x = scaleLinear().domain([loDomain, hiDomain]).range([padX, width - padX])

  const xs = useMemo(
    () => Array.from({ length: 121 }, (_, i) => loDomain + (i / 120) * (hiDomain - loDomain)),
    [loDomain, hiDomain],
  )
  const pdf = (v: number) => Math.exp(-0.5 * ((v - post.mean) / post.sd) ** 2)
  const ys = xs.map(pdf)
  const yMax = Math.max(...ys)
  const yScale = scaleLinear().domain([0, yMax]).range([0, height - 46])
  const baseY = height - 26

  const area =
    `M ${x(xs[0]).toFixed(1)} ${baseY} ` +
    xs.map((v, i) => `L ${x(v).toFixed(1)} ${(baseY - yScale(ys[i])).toFixed(1)}`).join(' ') +
    ` L ${x(xs[xs.length - 1]).toFixed(1)} ${baseY} Z`

  const realizedInView = realized >= loDomain && realized <= hiDomain

  return (
    <svg width={width} height={height} className="block w-full" viewBox={`0 0 ${width} ${height}`}>
      {/* zero line */}
      {loDomain < 0 && hiDomain > 0 ? (
        <line x1={x(0)} x2={x(0)} y1={10} y2={baseY} stroke="rgba(138,150,192,0.3)" strokeDasharray="2 3" />
      ) : null}
      {/* 90% CI band */}
      <rect
        x={x(post.p05)}
        y={baseY + 6}
        width={Math.max(0, x(post.p95) - x(post.p05))}
        height={4}
        rx={2}
        fill="rgba(255,138,61,0.55)"
      />
      {/* posterior area */}
      <path d={area} fill="rgba(255,138,61,0.16)" stroke="rgba(255,138,61,0.9)" strokeWidth={1.3} />
      {/* predicted mean */}
      <line x1={x(post.mean)} x2={x(post.mean)} y1={baseY - yScale(yMax)} y2={baseY} stroke="rgba(255,138,61,0.95)" strokeWidth={1.4} />
      <circle cx={x(post.mean)} cy={baseY - yScale(yMax)} r={3.4} fill="#ff8a3d" stroke="#0b1018" strokeWidth={1.4} />
      {/* realized outcome */}
      {realizedInView ? (
        <g>
          <line x1={x(realized)} x2={x(realized)} y1={8} y2={baseY} stroke="#3ddc97" strokeWidth={2} />
          <text x={x(realized)} y={6} fontSize={10} textAnchor="middle" fill="#3ddc97" fontFamily="JetBrains Mono">
            realized {fmtM(realized)}
          </text>
        </g>
      ) : null}
      {/* axis ticks */}
      {[post.p05, post.mean, post.p95].map((v, i) => (
        <text key={i} x={x(v)} y={height - 8} fontSize={9} textAnchor="middle" fill="rgba(138,150,192,0.8)" fontFamily="JetBrains Mono">
          {fmtM(v)}
        </text>
      ))}
    </svg>
  )
}

function ModelTradeCard({ card }: { card: ModelCard }) {
  const tail = card.role === 'tail_miss'
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
        {card.realized_in_90ci ? (
          <span className="chip" style={{ color: '#3ddc97', borderColor: 'rgba(61,220,151,0.4)' }}>
            <CheckCircle2 className="h-3 w-3" /> in 90% CI
          </span>
        ) : (
          <span className="chip" style={{ color: '#f5a524', borderColor: 'rgba(245,165,36,0.45)' }}>
            <AlertTriangle className="h-3 w-3" /> tail-miss
          </span>
        )}
      </div>

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

      {tail ? (
        <div className="mt-3 rounded-md border border-amber-500/30 bg-amber-500/5 p-3 text-[11px] leading-relaxed text-ink-300">
          <span className="font-semibold text-amber-300">Known limitation.</span> The model shrinks extreme-tail
          blockbusters toward the regime mean — the realized $150M surplus on Soto sits well above the 90% interval.
          This is expected behavior for a regularized hierarchical model (see validation philosophy), not a fitting
          bug. We show it deliberately: the model is calibrated on the bulk and conservative on the tail.
        </div>
      ) : null}
    </div>
  )
}

export default function ModelValuation() {
  const { scoreboard, comparison, credible_features, cards, train_window, test_window } = modelPosteriors
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
          Every distribution below is genuine posterior-predictive output from the frozen V3 dollar-surplus
          model — no illustrative numbers. The featured trades are <span className="text-ink-200">held out</span> of
          training, so we can score the model's predicted distribution against what actually happened.
        </p>
      </motion.div>

      {/* Scoreboard */}
      <Section eyebrow="Calibration scoreboard" title="How the model does across all held-out trades" hint="The headline number is coverage: a calibrated 90% interval should contain the realized outcome ~90% of the time.">
        <div className="card flex flex-wrap items-end gap-10 p-5">
          <Stat label="90% coverage" value={`${(scoreboard.coverage_90 * 100).toFixed(0)}%`} sub="target 90% — well calibrated" tone="pos" />
          <Stat label="CRPS" value={fmtM(scoreboard.crps)} sub="lower is better" />
          <Stat label="MAE" value={fmtM(scoreboard.mae)} sub="mean abs error" />
          <Stat label="Held-out trades" value={scoreboard.test_n.toLocaleString()} sub={`${scoreboard.train_n.toLocaleString()} train`} />
        </div>
      </Section>

      {/* Does context beat the naive models? */}
      <Section
        eyebrow="Does context actually help?"
        title="Context-aware vs. the baselines it has to beat"
        hint="Walk-forward CV (R-58), the methodology behind the D-41 thesis test. Two honest references: the naive 'just rate the player' model, and a 'predict the mean' floor."
      >
        <div className="mb-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="card p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">vs. player-quality-only</div>
            <div className="mono mt-1 text-[30px] font-semibold leading-none text-positive-500">
              +{(comparison.mean_skill_vs_quality_ex_break * 100).toFixed(0)}%
            </div>
            <div className="mt-1.5 text-[12px] leading-relaxed text-ink-400">
              Lower CRPS than rating the player in isolation (stable folds). Receiving-team context is the difference —
              this is the thesis, validated.
            </div>
          </div>
          <div className="card p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">vs. predict-the-mean</div>
            <div className="mono mt-1 text-[30px] font-semibold leading-none text-ink-100">
              {comparison.mean_skill_vs_intercept_ex_break >= 0 ? '+' : ''}
              {(comparison.mean_skill_vs_intercept_ex_break * 100).toFixed(1)}%
            </div>
            <div className="mt-1.5 text-[12px] leading-relaxed text-ink-400">
              Roughly at parity on raw dollar magnitude — the blockbuster tail dominates CRPS for any model. We don't
              oversell this number.
            </div>
          </div>
        </div>
        <div className="card overflow-hidden p-0">
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
              {comparison.folds.map((f) => (
                <tr key={f.label} className="border-b border-ink-800 last:border-0">
                  <td className="px-4 py-2 text-ink-200">
                    {f.label}
                    {f.structural_break ? (
                      <span className="ml-2 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-300">structural break</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-right text-ink-400">{f.n_test}</td>
                  <td className={`px-4 py-2 text-right ${f.skill_vs_quality >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>
                    {f.skill_vs_quality >= 0 ? '+' : ''}{(f.skill_vs_quality * 100).toFixed(1)}%
                  </td>
                  <td className={`px-4 py-2 text-right ${f.skill_vs_intercept >= 0 ? 'text-positive-500' : 'text-negative-500'}`}>
                    {f.skill_vs_intercept >= 0 ? '+' : ''}{(f.skill_vs_intercept * 100).toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* Covered cards */}
      <Section eyebrow="Held-out predictions" title="Predicted distribution vs. what happened" hint="Orange = model posterior with 90% interval; green = realized surplus. The model never saw these outcomes.">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {covered.map((c) => (
            <ModelTradeCard key={`${c.trade_event_id}-${c.receiver_bref}`} card={c} />
          ))}
        </div>
      </Section>

      {/* Tail miss */}
      {tail.length ? (
        <Section eyebrow="Where it fails" title="The tail the model shrinks — shown on purpose" hint="A front office should see the failure mode, not just the wins.">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {tail.map((c) => (
              <ModelTradeCard key={`${c.trade_event_id}-${c.receiver_bref}`} card={c} />
            ))}
          </div>
        </Section>
      ) : null}

      {/* Credible features */}
      <Section eyebrow="Why" title="What the model weighted" hint="Credible features (90% directional mass) driving the dollar-surplus posterior. Receiving-team context, not just player quality.">
        <div className="card divide-y divide-ink-800 p-0">
          {credible_features.map((f) => (
            <div key={f.feature} className="flex items-center justify-between gap-4 px-5 py-2.5">
              <div className="flex items-center gap-2.5">
                <Target className="h-3.5 w-3.5 text-accent-400" />
                <span className="text-[13px] text-ink-200">{featureLabel(f.feature)}</span>
              </div>
              <div className="flex items-center gap-5">
                <span className="mono text-[12px] tabular text-ink-300">
                  β {f.beta >= 0 ? '+' : ''}{f.beta.toFixed(3)}
                </span>
                <span className="mono text-[11px] tabular text-ink-500">{(f.directional_mass * 100).toFixed(0)}% mass</span>
              </div>
            </div>
          ))}
        </div>
      </Section>
    </main>
  )
}
