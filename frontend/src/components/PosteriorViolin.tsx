import { useMemo } from 'react'
import { scaleLinear } from 'd3-scale'

/**
 * A pseudo-posterior violin drawn from (mean, sd) — visual stand-in for the
 * real PPC distribution that will land in V2. Surfaces the design D-13 commits
 * to: every projected metric appears as a distribution, never a bare point.
 */
type Props = {
  mean: number
  sd: number
  min: number
  max: number
  baseline?: number | null
  width?: number
  height?: number
  accent?: 'pos' | 'neg' | 'neutral'
  label?: string
  unit?: string
}

const ACCENT: Record<NonNullable<Props['accent']>, { fill: string; stroke: string }> = {
  pos: { fill: 'rgba(61,220,151,0.18)', stroke: 'rgba(61,220,151,0.85)' },
  neg: { fill: 'rgba(255,93,115,0.16)', stroke: 'rgba(255,93,115,0.85)' },
  neutral: { fill: 'rgba(255,138,61,0.16)', stroke: 'rgba(255,138,61,0.85)' },
}

function pdf(x: number, mu: number, sd: number) {
  const z = (x - mu) / sd
  return Math.exp(-0.5 * z * z) / (sd * Math.sqrt(2 * Math.PI))
}

export function PosteriorViolin({
  mean,
  sd,
  min,
  max,
  baseline,
  width = 320,
  height = 64,
  accent = 'neutral',
  label,
  unit = '',
}: Props) {
  const palette = ACCENT[accent]
  const x = scaleLinear().domain([min, max]).range([0, width])
  const xs = useMemo(() => Array.from({ length: 81 }, (_, i) => min + (i / 80) * (max - min)), [min, max])
  const ys = xs.map((v) => pdf(v, mean, sd))
  const yMax = Math.max(...ys)
  const yScale = scaleLinear().domain([0, yMax]).range([0, height / 2 - 4])
  const path =
    xs.map((v, i) => `${i === 0 ? 'M' : 'L'} ${x(v).toFixed(2)} ${(height / 2 - yScale(ys[i])).toFixed(2)}`).join(' ') +
    ' ' +
    xs
      .slice()
      .reverse()
      .map((v, i) => `L ${x(v).toFixed(2)} ${(height / 2 + yScale(ys[xs.length - 1 - i])).toFixed(2)}`)
      .join(' ') +
    ' Z'

  // 90% CI band
  const lo = mean - 1.645 * sd
  const hi = mean + 1.645 * sd

  return (
    <div>
      {label ? <div className="mb-1.5 text-[11px] uppercase tracking-[0.12em] text-ink-400">{label}</div> : null}
      <svg width={width} height={height} className="block">
        {/* Zero line */}
        {min < 0 && max > 0 ? (
          <line x1={x(0)} x2={x(0)} y1={4} y2={height - 4} stroke="rgba(138,150,192,0.35)" strokeDasharray="2 3" />
        ) : null}
        {/* 90% CI */}
        <rect
          x={x(lo)}
          y={height / 2 - 1.5}
          width={Math.max(0, x(hi) - x(lo))}
          height={3}
          fill={palette.stroke}
          opacity={0.5}
          rx={1.5}
        />
        {/* Violin */}
        <path d={path} fill={palette.fill} stroke={palette.stroke} strokeWidth={1.2} />
        {/* Mean */}
        <circle cx={x(mean)} cy={height / 2} r={3.2} fill={palette.stroke} stroke="#0b1018" strokeWidth={1.5} />
        {/* Baseline marker */}
        {typeof baseline === 'number' ? (
          <g>
            <line
              x1={x(baseline)}
              x2={x(baseline)}
              y1={6}
              y2={height - 6}
              stroke="var(--color-baseline-500)"
              strokeWidth={1.5}
              strokeDasharray="3 2"
            />
            <text x={x(baseline) + 3} y={11} fontSize={9} fill="var(--color-baseline-500)" fontFamily="JetBrains Mono">
              baseline
            </text>
          </g>
        ) : null}
      </svg>
      <div className="mono mt-0.5 flex items-center justify-between text-[11px] tabular text-ink-300">
        <span>
          {mean >= 0 ? '+' : ''}
          {mean.toFixed(2)}
          {unit} <span className="text-ink-500">mean</span>
        </span>
        <span className="text-ink-400">
          [{lo.toFixed(2)}, {hi.toFixed(2)}] 90%
        </span>
      </div>
    </div>
  )
}
