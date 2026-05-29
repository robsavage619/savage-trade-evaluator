import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Clock, Tag } from 'lucide-react'
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis,
  Tooltip, ReferenceLine, CartesianGrid, Label, LabelList, ErrorBar,
  BarChart, Bar, Cell, Legend,
} from 'recharts'

// ── article JSON loader ───────────────────────────────────────────────────────

const ARTICLES: Record<string, () => Promise<{ default: Article }>> = {
  'reliever-war-illusion': () => import('../data/research/reliever-war-illusion.json'),
  'change-of-scenery-myth': () => import('../data/research/change-of-scenery-myth.json'),
  'pitching-coach-mirage': () => import('../data/research/pitching-coach-mirage.json'),
  'gm-edge-decomposition': () => import('../data/research/gm-edge-decomposition.json'),
  'gm-trade-ranking': () => import('../data/research/gm-trade-ranking.json'),
  'international-pitcher-pipeline': () => import('../data/research/international-pitcher-pipeline.json'),
  'award-breadth-vs-depth': () => import('../data/research/award-breadth-vs-depth.json'),
  'k-trajectory-split': () => import('../data/research/k-trajectory-split.json'),
}

// ── types ─────────────────────────────────────────────────────────────────────

type ProseSection = { type: 'prose'; content: string }
type StatRowSection = { type: 'stat_row'; stats: { label: string; value: string; subtext?: string }[] }
type CalloutSection = { type: 'callout'; variant: 'finding' | 'methodology' | 'warning'; title: string; content: string }
type ChartSection = {
  type: 'chart'
  chart_type: 'scatter' | 'bar' | 'grouped_bar' | 'horizontal_bar' | 'forest'
  title: string
  x_key: string
  y_key?: string
  y_keys?: string[]
  y_labels?: string[]
  label_key?: string
  size_key?: string
  highlight_labels?: string[]
  lo_key?: string
  hi_key?: string
  x_label?: string
  y_label?: string
  caption: string
  data: Record<string, number | string>[]
}

type ArticleSection = ProseSection | StatRowSection | CalloutSection | ChartSection

type Article = {
  slug: string
  title: string
  subtitle: string
  published_at: string
  tags: string[]
  read_time_minutes: number
  sections: ArticleSection[]
  methodology_note: string
}

// ── section renderers ─────────────────────────────────────────────────────────

function Prose({ content }: { content: string }) {
  return (
    <div className="space-y-4">
      {content.split('\n\n').map((para, i) => (
        <p key={i} className="text-[15px] leading-[1.75] text-ink-200">{para}</p>
      ))}
    </div>
  )
}

function StatRow({ stats }: { stats: StatRowSection['stats'] }) {
  return (
    <div className="flex flex-wrap gap-3 py-2">
      {stats.map((s) => (
        <div key={s.label} className="flex flex-col gap-0.5 rounded-lg border border-ink-700 bg-ink-800/60 px-5 py-3 min-w-[140px]">
          <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-ink-400">{s.label}</span>
          <span className="mono text-[15px] font-semibold text-ink-100">{s.value}</span>
          {s.subtext && <span className="text-[10px] text-ink-500">{s.subtext}</span>}
        </div>
      ))}
    </div>
  )
}

const CALLOUT_STYLES = {
  finding: 'border-accent-500/25 bg-accent-500/6',
  methodology: 'border-ink-600 bg-ink-800/50',
  warning: 'border-yellow-500/25 bg-yellow-500/6',
}
const CALLOUT_TITLE_STYLES = {
  finding: 'text-accent-400',
  methodology: 'text-ink-300',
  warning: 'text-yellow-400',
}

function Callout({ variant, title, content }: CalloutSection) {
  return (
    <div className={`rounded-lg border px-6 py-5 ${CALLOUT_STYLES[variant]}`}>
      <div className={`mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] ${CALLOUT_TITLE_STYLES[variant]}`}>{title}</div>
      <p className="text-[14px] leading-relaxed text-ink-200">{content}</p>
    </div>
  )
}

function ScatterPlot({ section }: { section: ChartSection }) {
  const highlights = new Set(section.highlight_labels ?? [])
  const labelKey = section.label_key
  const renderLabel = labelKey && highlights.size > 0
    ? (props: { x?: number; y?: number; value?: string | number }) => {
        const { x, y, value } = props
        if (typeof x !== 'number' || typeof y !== 'number') return <g />
        if (!highlights.has(String(value))) return <g />
        return (
          <text x={x + 8} y={y + 3} fill="#dce3f5" fontSize={10} fontWeight={500}>{String(value)}</text>
        )
      }
    : null
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-5">
      <div className="mb-1 text-[12px] font-semibold text-ink-100">{section.title}</div>
      <ResponsiveContainer width="100%" height={380}>
        <ScatterChart margin={{ top: 16, right: 60, bottom: 40, left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.07)" />
          <XAxis type="number" dataKey={section.x_key} stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.x_label && <Label value={section.x_label} position="bottom" offset={24} fill="#8a96c0" fontSize={11} />}
          </XAxis>
          <YAxis type="number" dataKey={section.y_key!} stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.y_label && <Label value={section.y_label} angle={-90} position="left" offset={28} fill="#8a96c0" fontSize={11} />}
          </YAxis>
          {section.size_key && <ZAxis dataKey={section.size_key} range={[40, 300]} />}
          <ReferenceLine y={0} stroke="rgba(138,150,192,0.3)" />
          <ReferenceLine x={0} stroke="rgba(138,150,192,0.15)" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => {
            const p = payload?.[0]?.payload
            if (!p) return null
            return (
              <div className="card px-3 py-2 text-[11px]">
                {labelKey && <div className="font-semibold text-ink-100">{p[labelKey]}</div>}
                <div className="mono mt-1 tabular text-ink-300">
                  {section.x_label}: {(p[section.x_key] as number).toFixed(3)}
                </div>
                <div className="mono tabular text-ink-300">
                  {section.y_label}: {(p[section.y_key!] as number).toFixed(3)}
                </div>
                {section.size_key && <div className="mono tabular text-ink-400">n={p[section.size_key]}</div>}
              </div>
            )
          }} />
          <Scatter data={section.data as Record<string, number>[]} fill="rgba(255,138,61,0.55)">
            {renderLabel && labelKey && <LabelList dataKey={labelKey} content={renderLabel as never} />}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">{section.caption}</p>
    </div>
  )
}

function HorizontalBarPlot({ section }: { section: ChartSection }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-5">
      <div className="mb-1 text-[12px] font-semibold text-ink-100">{section.title}</div>
      <ResponsiveContainer width="100%" height={Math.max(280, section.data.length * 28 + 60)}>
        <BarChart
          data={section.data as Record<string, number | string>[]}
          layout="vertical"
          margin={{ top: 12, right: 60, bottom: 40, left: 180 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.07)" />
          <XAxis type="number" stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.x_label && <Label value={section.x_label} position="bottom" offset={24} fill="#8a96c0" fontSize={11} />}
          </XAxis>
          <YAxis type="category" dataKey={section.x_key} stroke="#8a96c0" tick={{ fontSize: 11 }} width={170} />
          <ReferenceLine x={0} stroke="rgba(138,150,192,0.4)" />
          <Tooltip content={({ payload }) => {
            const p = payload?.[0]?.payload
            if (!p) return null
            return (
              <div className="card px-3 py-2 text-[11px]">
                <div className="font-semibold text-ink-100">{p[section.x_key]}</div>
                <div className="mono mt-1 tabular text-ink-300">{(p[section.y_key!] as number).toFixed(3)}</div>
              </div>
            )
          }} />
          <Bar dataKey={section.y_key!} radius={[0, 3, 3, 0]}>
            {(section.data as Record<string, number | string>[]).map((entry, i) => {
              const v = entry[section.y_key!] as number
              const fill = v >= 0.25 ? 'rgba(255,138,61,0.85)'
                : v >= 0 ? 'rgba(255,138,61,0.45)'
                : 'rgba(91,134,255,0.65)'
              return <Cell key={i} fill={fill} />
            })}
            <LabelList
              dataKey={section.y_key!}
              position="right"
              formatter={(v: number) => v.toFixed(2)}
              style={{ fill: '#8a96c0', fontSize: 10 }}
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">{section.caption}</p>
    </div>
  )
}

function BarPlot({ section }: { section: ChartSection }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-5">
      <div className="mb-1 text-[12px] font-semibold text-ink-100">{section.title}</div>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={section.data as Record<string, number | string>[]} margin={{ top: 12, right: 24, bottom: 40, left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.07)" />
          <XAxis dataKey={section.x_key} stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.x_label && <Label value={section.x_label} position="bottom" offset={24} fill="#8a96c0" fontSize={11} />}
          </XAxis>
          <YAxis stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.y_label && <Label value={section.y_label} angle={-90} position="left" offset={28} fill="#8a96c0" fontSize={11} />}
          </YAxis>
          <ReferenceLine y={0} stroke="rgba(138,150,192,0.4)" />
          <Tooltip content={({ payload }) => {
            const p = payload?.[0]?.payload
            if (!p) return null
            return (
              <div className="card px-3 py-2 text-[11px]">
                <div className="font-semibold text-ink-100">{p[section.x_key]}</div>
                <div className="mono mt-1 tabular text-ink-300">{p[section.y_key!]}</div>
              </div>
            )
          }} />
          <Bar dataKey={section.y_key!} radius={[4, 4, 0, 0]}>
            {(section.data as Record<string, number | string>[]).map((entry, i) => (
              <Cell key={i} fill={(entry[section.y_key!] as number) >= 0 ? 'rgba(255,138,61,0.7)' : 'rgba(91,134,255,0.6)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">{section.caption}</p>
    </div>
  )
}

function GroupedBarPlot({ section }: { section: ChartSection }) {
  const keys = section.y_keys ?? []
  const labels = section.y_labels ?? keys
  const COLORS = ['rgba(91,134,255,0.75)', 'rgba(255,138,61,0.75)']
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-5">
      <div className="mb-1 text-[12px] font-semibold text-ink-100">{section.title}</div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={section.data as Record<string, number | string>[]} margin={{ top: 12, right: 24, bottom: 40, left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.07)" />
          <XAxis dataKey={section.x_key} stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.x_label && <Label value={section.x_label} position="bottom" offset={24} fill="#8a96c0" fontSize={11} />}
          </XAxis>
          <YAxis stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.y_label && <Label value={section.y_label} angle={-90} position="left" offset={28} fill="#8a96c0" fontSize={11} />}
          </YAxis>
          <ReferenceLine y={0} stroke="rgba(138,150,192,0.4)" />
          <Legend formatter={(v: string) => labels[keys.indexOf(v)] ?? v} wrapperStyle={{ fontSize: 11, color: '#8a96c0' }} />
          <Tooltip content={({ payload }) => {
            const p = payload?.[0]?.payload
            if (!p) return null
            return (
              <div className="card px-3 py-2 text-[11px]">
                <div className="font-semibold text-ink-100">{p[section.x_key]}</div>
                {keys.map((k, i) => (
                  <div key={k} className="mono tabular text-ink-300">{labels[i]}: {(p[k] as number).toFixed(3)}</div>
                ))}
              </div>
            )
          }} />
          {keys.map((k, i) => (
            <Bar key={k} dataKey={k} fill={COLORS[i]} radius={[3, 3, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">{section.caption}</p>
    </div>
  )
}

function ForestPlot({ section }: { section: ChartSection }) {
  // x = effect; y = label (category)
  const data = (section.data as Record<string, number | string>[]).map((d) => {
    const mean = d[section.y_key!] as number
    const lo = d[section.lo_key!] as number
    const hi = d[section.hi_key!] as number
    return { ...d, _err: [mean - lo, hi - mean] }
  })
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-5">
      <div className="mb-1 text-[12px] font-semibold text-ink-100">{section.title}</div>
      <ResponsiveContainer width="100%" height={Math.max(300, data.length * 22 + 80)}>
        <ScatterChart layout="vertical" margin={{ top: 12, right: 30, bottom: 40, left: 160 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(138,150,192,0.07)" />
          <XAxis type="number" dataKey={section.y_key!} stroke="#5a6896" tick={{ fontSize: 11 }}>
            {section.x_label && <Label value={section.x_label} position="bottom" offset={24} fill="#8a96c0" fontSize={11} />}
          </XAxis>
          <YAxis type="category" dataKey={section.x_key} stroke="#8a96c0" tick={{ fontSize: 10 }} width={150} interval={0} />
          <ReferenceLine x={0} stroke="rgba(138,150,192,0.45)" strokeDasharray="2 2" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} content={({ payload }) => {
            const p = payload?.[0]?.payload
            if (!p) return null
            return (
              <div className="card px-3 py-2 text-[11px]">
                <div className="font-semibold text-ink-100">{p[section.x_key]}</div>
                <div className="mono mt-1 tabular text-ink-300">{(p[section.y_key!] as number).toFixed(3)} [{(p[section.lo_key!] as number).toFixed(2)}, {(p[section.hi_key!] as number).toFixed(2)}]</div>
                {section.size_key && <div className="mono tabular text-ink-400">n = {p[section.size_key]}</div>}
              </div>
            )
          }} />
          <Scatter data={data} fill="rgba(255,138,61,0.9)" shape="circle">
            <ErrorBar dataKey="_err" width={0} stroke="rgba(255,138,61,0.55)" strokeWidth={2} direction="x" />
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="mt-2 text-[11px] leading-relaxed text-ink-500">{section.caption}</p>
    </div>
  )
}

function ArticleChart({ section }: { section: ChartSection }) {
  if (section.chart_type === 'scatter') return <ScatterPlot section={section} />
  if (section.chart_type === 'grouped_bar') return <GroupedBarPlot section={section} />
  if (section.chart_type === 'horizontal_bar') return <HorizontalBarPlot section={section} />
  if (section.chart_type === 'forest') return <ForestPlot section={section} />
  return <BarPlot section={section} />
}

function Section({ section }: { section: ArticleSection }) {
  if (section.type === 'prose') return <Prose content={section.content} />
  if (section.type === 'stat_row') return <StatRow stats={section.stats} />
  if (section.type === 'callout') return <Callout {...section} />
  if (section.type === 'chart') return <ArticleChart section={section} />
  return null
}

// ── page ──────────────────────────────────────────────────────────────────────

import { useEffect, useState } from 'react'

export default function ResearchArticle() {
  const { slug } = useParams<{ slug: string }>()
  const [article, setArticle] = useState<Article | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    const loader = slug ? ARTICLES[slug] : undefined
    if (!loader) { setNotFound(true); return }
    loader().then((m) => setArticle(m.default)).catch(() => setNotFound(true))
  }, [slug])

  if (notFound) {
    return (
      <main className="mx-auto max-w-[780px] px-6 py-24 text-center">
        <div className="text-[13px] text-ink-400">Article not found</div>
        <Link to="/research" className="mt-4 inline-flex items-center gap-1.5 text-[13px] text-accent-400 hover:text-accent-300">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Research
        </Link>
      </main>
    )
  }

  if (!article) {
    return (
      <main className="mx-auto max-w-[780px] px-6 py-24 text-center text-[13px] text-ink-500">
        Loading…
      </main>
    )
  }

  return (
    <main className="mx-auto max-w-[780px] px-6 py-12 pb-24">
      {/* Back link */}
      <Link to="/research" className="mb-8 inline-flex items-center gap-1.5 text-[12px] text-ink-400 hover:text-ink-200 transition-colors">
        <ArrowLeft className="h-3.5 w-3.5" /> Research
      </Link>

      {/* Header */}
      <header className="mb-10 border-b border-ink-700 pb-8">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          {article.tags.map((t) => (
            <span key={t} className="flex items-center gap-1 rounded-full border border-ink-700 px-2.5 py-0.5 text-[10px] font-medium text-ink-400">
              <Tag className="h-2.5 w-2.5" />{t}
            </span>
          ))}
          <span className="flex items-center gap-1 text-[10px] text-ink-500">
            <Clock className="h-2.5 w-2.5" />{article.read_time_minutes} min read
          </span>
        </div>
        <h1 className="text-[36px] font-semibold leading-tight tracking-tight text-ink-100">{article.title}</h1>
        <p className="mt-3 text-[17px] leading-relaxed text-ink-300">{article.subtitle}</p>
        <div className="mt-4 text-[11px] text-ink-500">
          {new Date(article.published_at).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })} · Savage Analytics
        </div>
      </header>

      {/* Body */}
      <div className="space-y-8">
        {article.sections.map((s, i) => (
          <Section key={i} section={s} />
        ))}
      </div>

      {/* Methodology note */}
      <div className="mt-12 rounded-lg border border-ink-800 bg-ink-900 px-6 py-5">
        <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-500">Methodology</div>
        <p className="text-[12px] leading-relaxed text-ink-400">{article.methodology_note}</p>
      </div>
    </main>
  )
}
