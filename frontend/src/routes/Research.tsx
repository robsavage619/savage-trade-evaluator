import { Link } from 'react-router-dom'
import { Clock, Tag, ArrowRight, FlaskConical } from 'lucide-react'
import researchIndex from '../data/research/index.json'

type ArticleMeta = {
  slug: string
  title: string
  subtitle: string
  published_at: string
  tags: string[]
  summary: string
  read_time_minutes: number
}

const CORRECTIONS = [
  { id: 'D-24', correction: 'Within-team variation features beat static team features', lesson: 'Static features null in R-06/07/09/14 — R-15 first directional signal' },
  { id: 'D-26', correction: 'Rate-based outcomes required (xwOBA, K%, xERA)', lesson: 'R-19: 3 credible features on xwOBA-delta, 0 on WAR at same sample size' },
  { id: 'D-27', correction: 'Feature importance is outcome-specific — no global best set', lesson: 'R-22: K%-trajectory is 100% credible on kpct_delta, invisible on WAR' },
  { id: 'D-28', correction: 'GM regime explains 3× more variance than franchise identity', lesson: 'R-25/27: cluster on (team, regime), not just team' },
  { id: 'D-29', correction: 'System-tax thesis rejected — sell-high mechanism confirmed', lesson: 'R-30: young prospects positive in every regime; vets decline' },
]

function ArticleCard({ article }: { article: ArticleMeta }) {
  return (
    <Link
      to={`/research/${article.slug}`}
      className="group flex flex-col gap-4 rounded-xl border border-ink-700 bg-ink-900 p-6 transition-colors hover:border-accent-500/40 hover:bg-ink-800/60"
    >
      <div className="flex flex-wrap items-center gap-2">
        {article.tags.slice(0, 3).map((t) => (
          <span key={t} className="flex items-center gap-1 rounded-full border border-ink-700 px-2.5 py-0.5 text-[10px] font-medium text-ink-400">
            <Tag className="h-2.5 w-2.5" />{t}
          </span>
        ))}
        <span className="ml-auto flex items-center gap-1 text-[10px] text-ink-500">
          <Clock className="h-2.5 w-2.5" />{article.read_time_minutes} min
        </span>
      </div>

      <div>
        <h2 className="text-[20px] font-semibold leading-snug tracking-tight text-ink-100 group-hover:text-accent-300 transition-colors">
          {article.title}
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-400">{article.subtitle}</p>
      </div>

      <p className="text-[13px] leading-relaxed text-ink-300">{article.summary}</p>

      <div className="flex items-center justify-between">
        <span className="text-[11px] text-ink-500">
          {new Date(article.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
        </span>
        <span className="flex items-center gap-1 text-[12px] font-medium text-accent-400 opacity-0 transition-opacity group-hover:opacity-100">
          Read <ArrowRight className="h-3.5 w-3.5" />
        </span>
      </div>
    </Link>
  )
}

export default function Research() {
  const articles = researchIndex.articles as ArticleMeta[]

  return (
    <main className="relative">
      {/* Hero */}
      <div className="border-b border-ink-700 bg-ink-900 px-6 py-12">
        <div className="mx-auto max-w-[1100px]">
          <div className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">
            <FlaskConical className="h-3.5 w-3.5" />
            Savage Analytics Research
          </div>
          <h1 className="text-[36px] font-semibold tracking-tight text-ink-100">What the data actually says</h1>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-300">
            Data-driven research into MLB trade outcomes. Each article is grounded in Bayesian posterior estimates
            from 5,300+ trade legs — not intuition, not conventional wisdom.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <div className="flex flex-col gap-0.5 rounded-md border border-ink-700 bg-ink-800 px-4 py-3 min-w-[140px]">
              <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">Trade legs</span>
              <span className="mono text-[13px] font-semibold tabular text-ink-200">5,308</span>
            </div>
            <div className="flex flex-col gap-0.5 rounded-md border border-ink-700 bg-ink-800 px-4 py-3 min-w-[140px]">
              <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">Published articles</span>
              <span className="mono text-[13px] font-semibold tabular text-positive-500">{articles.length}</span>
            </div>
            <div className="flex flex-col gap-0.5 rounded-md border border-ink-700 bg-ink-800 px-4 py-3 min-w-[140px]">
              <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">Train window</span>
              <span className="mono text-[13px] font-semibold tabular text-ink-200">2010–2020</span>
            </div>
            <div className="flex flex-col gap-0.5 rounded-md border border-ink-700 bg-ink-800 px-4 py-3 min-w-[140px]">
              <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">Holdout</span>
              <span className="mono text-[13px] font-semibold tabular text-ink-200">2021–2024</span>
            </div>
          </div>
        </div>
      </div>

      {/* Article grid */}
      <div className="mx-auto max-w-[1100px] px-6 py-12">
        <h2 className="mb-6 text-[13px] font-semibold uppercase tracking-[0.18em] text-ink-400">Articles</h2>
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3">
          {articles.map((a) => (
            <ArticleCard key={a.slug} article={a} />
          ))}
        </div>
      </div>

      {/* Research log — condensed */}
      <div className="border-t border-ink-800 mx-auto max-w-[1100px] px-6 py-10">
        <h2 className="mb-1 text-[13px] font-semibold uppercase tracking-[0.18em] text-ink-400">Research Log</h2>
        <p className="mb-5 text-[13px] text-ink-500">31 rounds · 5 methodology corrections · 1 thesis rejected</p>
        <div className="card overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-ink-800 text-[10px] uppercase tracking-[0.12em] text-ink-400">
              <tr>
                <th className="px-4 py-2.5 text-left">Decision</th>
                <th className="px-4 py-2.5 text-left">What changed</th>
                <th className="px-4 py-2.5 text-left">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-700/60">
              {CORRECTIONS.map((c) => (
                <tr key={c.id} className="hover:bg-ink-800/40">
                  <td className="px-4 py-3">
                    <span className="mono mr-2 rounded bg-ink-700 px-1.5 py-0.5 text-[10px] text-ink-300">{c.id}</span>
                    <span className="text-ink-100">{c.correction}</span>
                  </td>
                  <td className="px-4 py-3 text-ink-400">{c.lesson}</td>
                  <td className="px-4 py-3 text-ink-500 text-[11px] italic">see ADR log</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  )
}
