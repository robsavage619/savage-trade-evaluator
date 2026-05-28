import { useMemo } from 'react'
import { scaleLinear } from 'd3-scale'

const W = 460
const H = 130
const PAD_X = 8
const PAD_TOP = 20
const PAD_BOT = 22
const N_BINS = 22

function buildBins(draws: number[]) {
  // Clip display to p01–p99 so extreme tail draws don't blow the x-axis scale
  const p01 = draws[Math.max(0, Math.floor(draws.length * 0.01))]
  const p99 = draws[Math.min(draws.length - 1, Math.floor(draws.length * 0.99))]
  const lo = p01
  const hi = p99
  const step = (hi - lo) / N_BINS
  const bins = Array.from({ length: N_BINS }, (_, i) => ({
    x0: lo + i * step,
    x1: lo + (i + 1) * step,
    count: 0,
  }))
  for (const d of draws) {
    if (d < lo || d > hi) continue
    const i = Math.min(Math.floor((d - lo) / step), N_BINS - 1)
    bins[i].count++
  }
  return { bins, lo, hi, step }
}

type Props = {
  draws: number[]
  realized: number | null
  p05: number
  p95: number
  mean: number
  formatter?: (v: number, signed?: boolean) => string
}

export function DrawsHistogram({ draws, realized, p05, p95, mean, formatter = (v) => v.toFixed(2) }: Props) {
  const plotW = W - PAD_X * 2
  const plotH = H - PAD_TOP - PAD_BOT

  const { bins, lo, hi } = useMemo(() => buildBins(draws), [draws])
  const maxCount = Math.max(...bins.map((b) => b.count))

  const x = scaleLinear().domain([lo, hi]).range([PAD_X, W - PAD_X])
  const y = scaleLinear().domain([0, maxCount]).range([plotH, 0])

  const ciX1 = x(Math.max(p05, lo))
  const ciX2 = x(Math.min(p95, hi))
  const meanX = x(mean)
  const realizedInView = realized != null && realized >= lo && realized <= hi

  return (
    <svg width={W} height={H} className="block w-full" viewBox={`0 0 ${W} ${H}`}>
      {/* 90% CI background */}
      <rect
        x={ciX1}
        y={PAD_TOP}
        width={Math.max(0, ciX2 - ciX1)}
        height={plotH}
        fill="rgba(255,138,61,0.07)"
      />

      {/* CI band at bottom */}
      <rect
        x={ciX1}
        y={PAD_TOP + plotH + 5}
        width={Math.max(0, ciX2 - ciX1)}
        height={3}
        rx={1.5}
        fill="rgba(255,138,61,0.45)"
      />

      {/* Zero reference */}
      {lo < 0 && hi > 0 && (
        <line
          x1={x(0)}
          x2={x(0)}
          y1={PAD_TOP}
          y2={PAD_TOP + plotH}
          stroke="rgba(138,150,192,0.25)"
          strokeDasharray="2 3"
        />
      )}

      {/* Histogram bars */}
      {bins.map((b, i) => {
        const bx = x(b.x0)
        const bw = Math.max(1, x(b.x1) - x(b.x0) - 0.8)
        const bh = plotH - y(b.count)
        const inCi = b.x0 >= p05 && b.x1 <= p95
        if (b.count === 0) return null
        return (
          <rect
            key={i}
            x={bx}
            y={PAD_TOP + y(b.count)}
            width={bw}
            height={bh}
            fill={inCi ? 'rgba(255,138,61,0.6)' : 'rgba(255,138,61,0.22)'}
            stroke="rgba(255,138,61,0.55)"
            strokeWidth={0.5}
            rx={0.8}
          />
        )
      })}

      {/* Mean marker */}
      <line x1={meanX} x2={meanX} y1={PAD_TOP} y2={PAD_TOP + plotH} stroke="rgba(255,138,61,0.9)" strokeWidth={1.3} />
      <circle cx={meanX} cy={PAD_TOP} r={2.8} fill="#ff8a3d" stroke="#0b1018" strokeWidth={1.2} />

      {/* Realized outcome */}
      {realizedInView && (
        <g>
          <line
            x1={x(realized!)}
            x2={x(realized!)}
            y1={PAD_TOP - 2}
            y2={PAD_TOP + plotH}
            stroke="#3ddc97"
            strokeWidth={2}
          />
          <text
            x={x(realized!)}
            y={PAD_TOP - 5}
            fontSize={9}
            textAnchor="middle"
            fill="#3ddc97"
            fontFamily="JetBrains Mono, monospace"
          >
            {formatter(realized!, false)}
          </text>
        </g>
      )}

      {/* X axis labels */}
      {([lo, mean, hi] as const).map((v, i) => (
        <text
          key={i}
          x={x(v)}
          y={H - 6}
          fontSize={9}
          textAnchor={i === 0 ? 'start' : i === 2 ? 'end' : 'middle'}
          fill="rgba(138,150,192,0.6)"
          fontFamily="JetBrains Mono, monospace"
        >
          {formatter(v, false)}
        </text>
      ))}

      {/* Caption: n draws */}
      <text x={W - PAD_X} y={PAD_TOP - 7} textAnchor="end" fontSize={8.5} fill="rgba(138,150,192,0.4)" fontFamily="JetBrains Mono, monospace">
        {draws.length} posterior draws
      </text>
    </svg>
  )
}
