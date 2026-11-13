import { motion } from 'framer-motion'
import { Sigma } from 'lucide-react'
import { Section, Stat } from '../components/Section'
import { validation } from '../lib/structuralData'

// Fold and context-test numbers are copied from docs/evaluation.md (R-64, R-65, R-66).
// The holdout row for the structural model comes from structural_validation.json.

const LADDER = [
  { spec: 'Null (median / climatology)', mae: '1.324', crps: '1.128', cov: '', win: false },
  { spec: 'A. Last-year WAR, plain regression', mae: '1.279', crps: '1.030', cov: '90.7%', win: false },
  { spec: 'B. Last-year WAR, two-part', mae: '1.241', crps: '0.984', cov: '91.7%', win: false },
  { spec: 'C. Structural, two-part', mae: '1.207', crps: '0.961', cov: '90.3%', win: true },
  { spec: 'D. The 34 context features, two-part', mae: '1.342', crps: '1.096', cov: '90.1%', win: false },
  { spec: 'E. Structural + 34 context, two-part', mae: '1.237', crps: '0.963', cov: '90.5%', win: false },
]

const CONTEXT_TESTS = [
  { spec: 'Context as an additive feature', gain: '-0.0040', half: '0.0051', folds: '0 of 4' },
  { spec: 'Context x held WAR', gain: '-0.0025', half: '0.0125', folds: '1 of 4' },
  { spec: 'Contention x held WAR', gain: '+0.0016', half: '0.0088', folds: '3 of 4' },
  { spec: 'Payroll x post-control held WAR', gain: '+0.0002', half: '0.0066', folds: '3 of 4' },
  { spec: 'Displaced WAR (who he would replace)', gain: '+0.0104', half: '0.0175', folds: '3 of 4' },
]

const pct = (a: number, b: number) => `${(((b - a) / b) * 100).toFixed(1)}%`

function Row({ cells, strong }: { cells: string[]; strong?: boolean }) {
  return (
    <tr className={`border-b border-ink-800 last:border-0 ${strong ? 'bg-accent-500/5 text-ink-100' : 'text-ink-300'}`}>
      {cells.map((c, i) => (
        <td key={i} className={`px-4 py-2 ${i === 0 ? 'text-left' : 'mono tabular text-right'}`}>
          {c}
        </td>
      ))}
    </tr>
  )
}

function Head({ cols }: { cols: string[] }) {
  return (
    <thead>
      <tr className="border-b border-ink-700 text-[10px] uppercase tracking-[0.08em] text-ink-400">
        {cols.map((c, i) => (
          <th key={c} className={`px-4 py-2 font-medium ${i === 0 ? 'text-left' : 'text-right'}`}>
            {c}
          </th>
        ))}
      </tr>
    </thead>
  )
}

export default function ModelValuation() {
  const v = validation
  return (
    <main className="mx-auto max-w-[1100px] px-6 py-8">
      <motion.div className="mb-8" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-accent-400">
          <Sigma className="h-3.5 w-3.5" /> The model · graded on trades it never saw
        </div>
        <h1 className="text-[26px] font-semibold tracking-tight text-ink-100">
          Four features beat the baselines. Everything else we tried did not.
        </h1>
        <p className="mt-2 max-w-[780px] text-[13px] leading-relaxed text-ink-400">
          Every trade is scored on one number: the WAR each side earns <span className="text-ink-200">for the club that
          receives the players</span>, from the trade season through five years later. The model is trained on trades
          before 2018 and graded on {v.n_sides.toLocaleString()} trade sides from {v.holdout}. The forecast in the Trade
          Builder is this model, not an approximation of it.
        </p>
      </motion.div>

      <Section
        eyebrow="Holdout scoreboard"
        title={`${v.holdout}, n = ${v.n_sides.toLocaleString()} trade sides`}
        hint="Lower MAE and CRPS are better. CRPS grades the whole distribution, so it punishes intervals that are too wide or too narrow."
      >
        <div className="card p-5">
          <div className="flex flex-wrap items-end gap-10">
            <Stat
              label="MAE vs median null"
              value={`${v.mae.toFixed(3)} vs ${v.mae_null.toFixed(3)}`}
              sub={`${pct(v.mae, v.mae_null)} better`}
              tone="pos"
            />
            <Stat
              label="CRPS vs training distribution"
              value={`${v.crps.toFixed(3)} vs ${v.crps_climatology.toFixed(3)}`}
              sub={`${pct(v.crps, v.crps_climatology)} better`}
              tone="pos"
            />
            <Stat
              label="90% interval coverage"
              value={`${(v.coverage_90 * 100).toFixed(1)}%`}
              sub="outcomes inside the stated 90% band"
              tone="pos"
            />
            <Stat
              label="Favoured side wins"
              value={`${(v.favoured_side_win_rate * 100).toFixed(0)}% ± ${(v.favoured_side_half_width * 100).toFixed(0)}`}
              sub={`of ${v.favoured_side_trades} two-sided trades: a lean, not a call`}
            />
          </div>
        </div>
        <div className="mt-2 rounded border border-ink-800 bg-ink-900/30 px-4 py-2.5 text-[11px] leading-relaxed text-ink-500">
          For comparison, the earlier 34-feature Bayesian model (V3) scored MAE 1.143, CRPS 1.026 and 83.5% coverage on
          the same rows: worse than both baselines. The production gate (<span className="mono">scripts/benchmark_vs_naive.py</span>)
          exits nonzero unless the model beats every baseline and covers at least 80%.
        </div>
      </Section>

      <Section
        eyebrow="How it was built"
        title="Start from the simplest model that could work, add only what beats it"
        hint="Compared on pre-2018 walk-forward folds (test seasons 2014 to 2017, n = 1,169) before the holdout was ever touched."
      >
        <div className="card overflow-hidden p-0">
          <table className="w-full text-[12px]">
            <Head cols={['Spec', 'MAE', 'CRPS', 'Cov 90']} />
            <tbody>
              {LADDER.map((r) => (
                <Row key={r.spec} cells={[r.spec, r.mae, r.crps, r.cov]} strong={r.win} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-ink-400">
          The winner prices a side in two steps: the chance it produces any WAR at all (many sides produce none),
          then a ridge regression on the sides that do, with an empirical residual distribution so the intervals are
          honest. Its four inputs are WAR held while the club controls the player, WAR held after control ends, the
          number of players, and how many have no MLB time.
        </p>
      </Section>

      <Section
        eyebrow="Does club context help?"
        title="Not measurably, and we checked it the hard way"
        hint="Each spec was fixed before scoring. To earn a look at the holdout it needed a 99% interval above zero on the paired CRPS gain and a win in at least 3 of 4 folds."
      >
        <div className="card overflow-hidden p-0">
          <table className="w-full text-[12px]">
            <Head cols={['Test on top of the structural model', 'CRPS gain', '99% half-width', 'Folds better']} />
            <tbody>
              {CONTEXT_TESTS.map((r) => (
                <Row key={r.spec} cells={[r.spec, r.gain, r.half, r.folds]} />
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[12px] leading-relaxed text-ink-400">
          No spec cleared the bar, so the holdout was never used to rescue one. The closest, displaced WAR, gains about
          1.1% but its interval runs from roughly -0.007 to +0.028. A planted effect of 10% of held WAR per standard
          deviation is detected by the same pipeline; 5% is not. So a context effect that large would have shown up, and
          smaller ones cannot be ruled out at this sample size.
        </p>
      </Section>

      <Section eyebrow="Correction" title="The first headline number was wrong">
        <div className="card p-5 text-[13px] leading-relaxed text-ink-300">
          An earlier version of the benchmark reported V3 beating a naive baseline by 28.2%. It scored a model that had
          trained through 2022 on 2018-2021 trades, and compared it with the training mean when the honest baseline was
          the median (43% of that earlier target's outcomes were zero). Refit on pre-2018 rows and compared fairly, V3 does not beat predicting
          zero. The structural model came from rebuilding with that discipline. Both reports are committed in the repo.
        </div>
      </Section>

      <Section eyebrow="What it does not see" title="Limits, stated where you use the model">
        <ul className="card space-y-2 p-5 text-[13px] leading-relaxed text-ink-300">
          <li>
            <span className="text-ink-100">Contracts.</span> A star on a long guarantee is priced like a typical veteran,
            and a rental or opt-out candidate as if he stays. The Trade Builder lists these players under Not in this
            forecast.
          </li>
          <li>
            <span className="text-ink-100">Acceptance.</span> It prices a trade; it cannot say whether the other club
            would take it. Refused proposals are not public.
          </li>
          <li>
            <span className="text-ink-100">Selection.</span> General managers chose these trades, so the numbers describe
            deals that happened, not deals in general.
          </li>
        </ul>
      </Section>
    </main>
  )
}
