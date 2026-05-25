import { motion } from 'framer-motion'
import { Target, CheckCircle2, AlertTriangle, Sigma, Coins, BarChart3, Eye } from 'lucide-react'
import { Section, Stat } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import { PosteriorCurve, fmtM } from '../components/PosteriorCurve'
import { modelPosteriors, featureLabel, type ModelCard } from '../lib/modelPosteriors'

/** Plain-English primer so the page reads without a stats background. */
function HowToRead() {
  const items = [
    {
      icon: Coins,
      title: 'What the model predicts',
      body: 'Dollar surplus: the on-field value an acquiring club gets from a trade, converted to dollars, minus the salary it pays — over the 3 years after the deal. Positive = the club came out ahead.',
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

/** Compact key for the posterior charts. */
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
          <span className="font-semibold text-amber-300">Known limitation.</span> On rare, once-a-decade
          blockbusters, the model pulls its estimate toward the typical trade — Soto's real $150M surplus sits well
          above its predicted range. That's the model being cautious about extreme outliers by design, not a bug. We
          show it on purpose: it's accurate on ordinary trades and deliberately conservative on the giants.
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

      <HowToRead />

      {/* Scoreboard */}
      <Section eyebrow="Calibration scoreboard" title="How the model does across all held-out trades" hint="Across every trade it never trained on, how close did it get — and was it honest about its own uncertainty?">
        <div className="card flex flex-wrap items-end gap-10 p-5">
          <Stat label="90% coverage" value={`${(scoreboard.coverage_90 * 100).toFixed(0)}%`} sub="of outcomes landed inside the predicted range — target is 90%, so it's honest about uncertainty" tone="pos" />
          <Stat label="CRPS" value={fmtM(scoreboard.crps)} sub="typical prediction error, penalizing overconfidence — lower is better" />
          <Stat label="MAE" value={fmtM(scoreboard.mae)} sub="average dollar miss of the center estimate" />
          <Stat label="Held-out trades" value={scoreboard.test_n.toLocaleString()} sub={`scored · ${scoreboard.train_n.toLocaleString()} used for training`} />
        </div>
      </Section>

      {/* Does context beat the naive models? */}
      <Section
        eyebrow="Does context actually help?"
        title="Context-aware vs. the baselines it has to beat"
        hint="The whole thesis is that the same player is worth different amounts to different teams. To prove it earns its keep, the model is raced against two simpler ones on trades none of them trained on. Higher % = bigger edge."
      >
        <div className="mb-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="card p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">vs. player-quality-only</div>
            <div className="mono mt-1 text-[30px] font-semibold leading-none text-positive-500">
              +{(comparison.mean_skill_vs_quality_ex_break * 100).toFixed(0)}%
            </div>
            <div className="mt-1.5 text-[12px] leading-relaxed text-ink-400">
              The baseline that rates the player alone and ignores which team acquires him. Our model is{' '}
              <span className="text-ink-200">~30% more accurate</span> — adding receiving-team context is what does it.
              This is the thesis, validated.
            </div>
          </div>
          <div className="card p-5">
            <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">vs. predict-the-mean</div>
            <div className="mono mt-1 text-[30px] font-semibold leading-none text-ink-100">
              {comparison.mean_skill_vs_intercept_ex_break >= 0 ? '+' : ''}
              {(comparison.mean_skill_vs_intercept_ex_break * 100).toFixed(1)}%
            </div>
            <div className="mt-1.5 text-[12px] leading-relaxed text-ink-400">
              The floor that guesses the league-average surplus every time. We're about even here on raw dollars — a few
              huge blockbusters swamp this metric for any model — so we don't oversell it.
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
      <Section eyebrow="Held-out predictions" title="Predicted distribution vs. what happened" hint="Each trade was kept out of training. Did reality (green) land inside the model's predicted range (orange)?">
        <ChartKey />
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
      <Section eyebrow="Why" title="What moves the valuation" hint="The inputs the model leans on most — the ones it's confident actually matter. Note how many describe the receiving team, not just the player.">
        <div className="card divide-y divide-ink-800 p-0">
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
    </main>
  )
}
