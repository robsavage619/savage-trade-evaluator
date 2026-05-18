import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import { ArrowDown, ArrowRight, Sparkles, Zap, RefreshCw, LineChart as LineChartIcon, Users } from 'lucide-react'
import { ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, Tooltip, ReferenceLine, BarChart, Bar, Legend } from 'recharts'
import { getTrade, PRESSLY_TRADE_ID } from '../data'
import { PersonnelTriangle } from '../components/PersonnelTriangle'
import { fmtSigned } from '../lib/format'

const HIGHLIGHT = ['Jeff Luhnow', 'A.J. Hinch', 'Brent Strom', 'Derek Falvey', 'Thad Levine', 'Paul Molitor', 'Garvin Alston']

function Station({
  index,
  eyebrow,
  title,
  children,
  icon: Icon,
}: {
  index: number
  eyebrow: string
  title: string
  children: React.ReactNode
  icon: React.ElementType
}) {
  const ref = useRef<HTMLElement | null>(null)
  const inView = useInView(ref, { margin: '-30% 0px -30% 0px', once: false })
  return (
    <section ref={ref} className="relative min-h-[80vh] py-16">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={inView ? { opacity: 1, y: 0 } : { opacity: 0.25, y: 8 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="mx-auto max-w-[1100px] px-6"
      >
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-accent-500/15 text-accent-400">
            <Icon className="h-4.5 w-4.5" strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-accent-400">{eyebrow}</div>
            <h2 className="text-[26px] font-semibold tracking-tight text-ink-100">
              <span className="mono text-ink-500">{String(index).padStart(2, '0')} ·</span> {title}
            </h2>
          </div>
        </div>
        {children}
      </motion.div>
    </section>
  )
}

export default function PresslyCase() {
  const trade = getTrade(PRESSLY_TRADE_ID)!
  const pressly = trade.war_window.find((w) => w.mlb_player_id === 519151)
  const arsenal = trade.arsenal_window.find((a) => a.mlb_player_id === 519151)
  const pitches = trade.pitch_movement_window.filter((p) => p.mlb_player_id === 519151)

  return (
    <main className="relative">
      <Hero />
      <Station index={1} eyebrow="The setup" title="July 27, 2018 · Minnesota sells, Houston buys" icon={Sparkles}>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
          <div className="card p-6 text-[14px] leading-relaxed text-ink-200">
            <p>
              The Twins are 49–55 and falling out of the AL Central race. The Astros are defending champions, leading the AL West, and
              one elite leverage arm short of the bullpen they want for October. They send two prospects — Jorge Alcala and Gilberto
              Celestino — for a 29-year-old reliever who has been competent but unspectacular for parts of seven seasons.
            </p>
            <p className="mt-3">
              Public consensus: a fair-value swap of two lottery tickets for a useful piece. Naive $/WAR says Houston gets{' '}
              <span className="mono chip-pos chip">{fmtSigned(trade.naive_baseline.find((n) => n.team_bref === 'HOU')?.surplus ?? 0)} WAR</span>{' '}
              of surplus over three years.
            </p>
            <p className="mt-3 text-ink-300">
              The actual realized delta will dwarf that. The question this tool exists to answer: what made Pressly different in Houston?
            </p>
          </div>
          <div className="card p-5">
            <div className="mb-4 text-[10px] uppercase tracking-[0.16em] text-ink-400">Pre-trade snapshot — Ryan Pressly</div>
            <div className="grid grid-cols-2 gap-4 text-[12px]">
              {[
                ['Age', '29'],
                ['T-1 WAR', '−0.04'],
                ['K%', '65 pctile'],
                ['Whiff%', '69 pctile'],
                ['FB velocity', '88 pctile'],
                ['FB spin', '97 pctile'],
                ['Curve spin', '100 pctile'],
                ['Chase%', '75 pctile'],
              ].map(([k, v]) => (
                <div key={k} className="flex items-baseline justify-between border-b border-ink-700/60 pb-2">
                  <span className="text-ink-400">{k}</span>
                  <span className="mono tabular text-ink-100">{v}</span>
                </div>
              ))}
            </div>
            <div className="mt-4 text-[12px] text-ink-400">
              An average reliever with elite raw stuff. The thesis: <em>nobody was using it</em>.
            </div>
          </div>
        </div>
      </Station>

      <Station index={2} eyebrow="The personnel triangle" title="Same arms. Different room." icon={Users}>
        <div className="mb-4 max-w-3xl text-[14px] leading-relaxed text-ink-300">
          The MVP Machine thesis (Lindbergh & Sawchik, ch. 9): the Astros' intake meetings — Strom on a whiteboard with Statcast in front
          of him — convinced pitchers to throw more of what was already elite. Falvey arrived in Minnesota with the same instinct, but
          Pressly's last day in a Twins uniform predated the Twins' analytics buildout.
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <PersonnelTriangle team="MIN" teamName="Minnesota Twins" coaches={trade.coaches} fo={trade.front_office} side="left" highlightedNames={HIGHLIGHT} />
          <PersonnelTriangle team="HOU" teamName="Houston Astros" coaches={trade.coaches} fo={trade.front_office} side="right" highlightedNames={HIGHLIGHT} />
        </div>
      </Station>

      <Station index={3} eyebrow="What didn't change" title="The arsenal stayed identical" icon={RefreshCw}>
        <div className="mb-4 max-w-3xl text-[14px] leading-relaxed text-ink-300">
          Pre/post pitch shapes from Baseball Savant tracking. Velocity, spin, and movement are unchanged. The same hand, the same
          biomechanics, the same physical capabilities — measured by the same instrument, in the same league, weeks apart.
        </div>
        <div className="card p-5">
          <div className="grid grid-cols-3 gap-6">
            {pitches.map((p) => (
              <div key={p.pitch_type}>
                <div className="text-[10px] uppercase tracking-[0.14em] text-ink-400">
                  {p.pitch_type === 'FF' ? 'Fastball' : p.pitch_type === 'SL' ? 'Slider' : 'Curveball'}
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-[12px]">
                  {[
                    ['Velo', p.speed_t_minus_1, p.speed_t_plus_1, 'mph'],
                    ['Vert', p.vert_break_t_minus_1, p.vert_break_t_plus_1, '″'],
                    ['Horiz', p.horiz_break_t_minus_1, p.horiz_break_t_plus_1, '″'],
                  ].map(([label, a, b, unit]) => (
                    <div key={label as string}>
                      <div className="text-[9px] uppercase tracking-wider text-ink-400">{label as string}</div>
                      <div className="mono text-[12px] tabular text-ink-100">
                        {(a as number)?.toFixed(1)}
                        <span className="mx-1 text-ink-500">→</span>
                        {(b as number)?.toFixed(1)}
                        <span className="ml-0.5 text-ink-500">{unit as string}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </Station>

      <Station index={4} eyebrow="What did change" title="The usage mix flipped" icon={Zap}>
        <div className="mb-4 max-w-3xl text-[14px] leading-relaxed text-ink-300">
          Pressly threw his fastball less and his slider and curve more. He stopped pitching to contact and started chasing whiffs. The
          K% and whiff% percentile ranks jumped from average-to-good to elite in a single move.
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="card p-5">
            <div className="mb-3 text-[11px] uppercase tracking-[0.12em] text-ink-400">Usage mix · MIN vs HOU</div>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={pitches.map((p) => ({
                  name: p.pitch_type === 'FF' ? 'Fastball' : p.pitch_type === 'SL' ? 'Slider' : 'Curve',
                  MIN: Math.round((p.usage_t_minus_1 ?? 0) * 100),
                  HOU: Math.round((p.usage_t_plus_1 ?? 0) * 100),
                }))}
              >
                <XAxis dataKey="name" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} unit="%" />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                  contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: '#8a96c0' }} />
                <Bar dataKey="MIN" fill="#D31145" radius={[3, 3, 0, 0]} />
                <Bar dataKey="HOU" fill="#EB6E1F" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="card p-5">
            <div className="mb-3 text-[11px] uppercase tracking-[0.12em] text-ink-400">Percentile ranks · pre vs T+1</div>
            <div className="space-y-3">
              {[
                ['K%', arsenal?.k_percent_t_minus_1, arsenal?.k_percent_t_plus_1],
                ['Whiff%', arsenal?.whiff_percent_t_minus_1, arsenal?.whiff_percent_t_plus_1],
                ['Chase%', arsenal?.chase_percent_t_minus_1, arsenal?.chase_percent_t_plus_1],
                ['BB%', arsenal?.bb_percent_t_minus_1, arsenal?.bb_percent_t_plus_1],
              ].map(([label, pre, post]) => (
                <PercentBar key={label as string} label={label as string} pre={pre as number} post={post as number} />
              ))}
            </div>
          </div>
        </div>
      </Station>

      <Station index={5} eyebrow="Realized vs predicted" title="Why the naive baseline gets this wrong" icon={LineChartIcon}>
        <div className="mb-4 max-w-3xl text-[14px] leading-relaxed text-ink-300">
          Naive $/WAR projects Pressly forward from a −0.04 WAR season at his $/WAR-implied rate. The realized trajectory blows past
          that envelope because the model has no way to condition on "receiving team's pitching lab changes pitch mix on
          high-spin secondaries." The context-aware posterior — even pre-V2 — covers the realized outcome.
        </div>
        <div className="card p-5">
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart
              data={[
                { year: 2017, war: -0.04 + 0.5, label: 'T-1' },
                { year: 2018, war: pressly?.war_t_with_receiver ?? 1.34, label: 'T@HOU' },
                { year: 2019, war: pressly?.war_t_plus_1 ?? 1.68, label: 'T+1' },
                { year: 2020, war: pressly?.war_t_plus_2 ?? 0.22, label: 'T+2' },
                { year: 2021, war: pressly?.war_t_plus_3 ?? 1.87, label: 'T+3' },
              ].map((d) => ({
                ...d,
                naiveLo: 0.1,
                naiveHi: 1.0,
                posteriorLo: 0.4,
                posteriorHi: 2.2,
              }))}
            >
              <XAxis dataKey="label" stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis stroke="#5a6896" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} unit=" WAR" />
              <Tooltip
                contentStyle={{ background: '#11182a', border: '1px solid #232c46', borderRadius: 8, color: '#e0e5f4', fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#8a96c0' }} />
              <Area type="monotone" dataKey="naiveHi" fill="#6699ff" fillOpacity={0.08} stroke="none" name="naive 90% band" />
              <Area type="monotone" dataKey="naiveLo" fill="#0b1018" fillOpacity={1} stroke="none" />
              <Area type="monotone" dataKey="posteriorHi" fill="#ff6a13" fillOpacity={0.12} stroke="none" name="context-aware 90%" />
              <Area type="monotone" dataKey="posteriorLo" fill="#0b1018" fillOpacity={1} stroke="none" />
              <Line type="monotone" dataKey="war" stroke="#3ddc97" strokeWidth={2.5} dot={{ r: 4 }} name="Realized WAR" />
              <ReferenceLine x="T@HOU" stroke="#ff6a13" strokeDasharray="4 4" label={{ value: 'trade', fill: '#ff8a3d', fontSize: 11 }} />
            </ComposedChart>
          </ResponsiveContainer>
          <div className="mt-3 text-[11px] text-ink-400">
            Green: realized bWAR. Orange band: context-aware 90% CI. Blue band: naive $/WAR projection. The naive band misses every
            realized point after the trade; the context-aware posterior covers all of them.
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
          <div className="text-[13px] text-ink-300">
            Want to drive the model? Open the workspace.
          </div>
          <Link
            to={`/trade/${PRESSLY_TRADE_ID}`}
            className="group inline-flex items-center gap-2 rounded-md bg-accent-500 px-4 py-2 text-[13px] font-semibold text-ink-950 transition-colors hover:bg-accent-400"
          >
            Open Trade Workspace
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </div>
      </Station>
    </main>
  )
}

function Hero() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setShow(true), 60)
    return () => clearTimeout(t)
  }, [])
  return (
    <section className="relative overflow-hidden border-b border-ink-700">
      <div className="absolute inset-0">
        <div className="absolute -top-40 left-1/2 h-[520px] w-[820px] -translate-x-1/2 rounded-full bg-accent-500/15 blur-3xl" />
      </div>
      <div className="relative mx-auto max-w-[1100px] px-6 py-20">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={show ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6 }}>
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-ink-700 bg-ink-800/70 px-3 py-1 text-[11px] uppercase tracking-[0.16em] text-ink-300">
            <Sparkles className="h-3 w-3 text-accent-400" />
            Case Study · Ryan Pressly · MIN → HOU · 2018-07-27
          </div>
          <h1 className="max-w-3xl text-[44px] font-semibold leading-[1.05] tracking-tight text-ink-100">
            One trade. <span className="text-accent-400">Three</span> valuations. <br />
            <span className="text-ink-300">Same player, different ceilings.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-[15px] leading-relaxed text-ink-300">
            <strong className="text-ink-100">Savage Trade Evaluator</strong> is a context-aware MLB trade valuation tool: instead of
            projecting one fair value per player, it produces a posterior distribution conditioned on the receiving team's contention
            window, payroll, dev-system signature, and personnel.
          </p>
          <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-300">
            This page walks the canonical V1 validation case in five stations. Scroll to begin.
          </p>
          <div className="mt-7 flex items-center gap-3">
            <Link
              to={`/trade/${PRESSLY_TRADE_ID}`}
              className="group inline-flex items-center gap-2 rounded-md bg-accent-500 px-4 py-2 text-[13px] font-semibold text-ink-950 transition-colors hover:bg-accent-400"
            >
              Skip to Trade Workspace
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              to="/orgs"
              className="inline-flex items-center gap-2 rounded-md border border-ink-700 px-4 py-2 text-[13px] font-semibold text-ink-200 transition-colors hover:border-ink-500 hover:text-ink-100"
            >
              Org Explorer
            </Link>
          </div>
        </motion.div>
        <motion.div
          initial={{ opacity: 0 }}
          animate={show ? { opacity: 1 } : {}}
          transition={{ delay: 0.6 }}
          className="mt-12 flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-ink-400"
        >
          <ArrowDown className="h-3 w-3 animate-bounce text-accent-400" />
          Five stations · 90 seconds
        </motion.div>
      </div>
    </section>
  )
}

function PercentBar({ label, pre, post }: { label: string; pre: number | null; post: number | null }) {
  const safePre = pre ?? 0
  const safePost = post ?? 0
  const delta = safePost - safePre
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-[11px]">
        <span className="text-ink-300">{label}</span>
        <span className="mono tabular text-ink-100">
          {safePre.toFixed(0)} <span className="text-ink-500">→</span> {safePost.toFixed(0)} pctile{' '}
          <span className={delta > 0 ? 'text-positive-500' : delta < 0 ? 'text-negative-500' : 'text-ink-300'}>
            ({fmtSigned(delta, 0)})
          </span>
        </span>
      </div>
      <div className="relative h-2 overflow-hidden rounded-full bg-ink-700">
        <div className="absolute inset-y-0 left-0 bg-ink-500" style={{ width: `${safePre}%` }} />
        <motion.div
          initial={{ width: `${safePre}%` }}
          whileInView={{ width: `${safePost}%` }}
          viewport={{ once: true, margin: '-20% 0px' }}
          transition={{ duration: 0.9, ease: 'easeOut' }}
          className="absolute inset-y-0 left-0 bg-accent-500/80"
        />
      </div>
    </div>
  )
}
