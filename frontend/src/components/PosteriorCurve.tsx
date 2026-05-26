import { useMemo } from 'react'
import { scaleLinear } from 'd3-scale'

const M = 1_000_000

export function fmtM(v: number, signed = false): string {
  const m = v / M
  const sign = signed && m >= 0 ? '+' : ''
  return `${sign}$${m.toFixed(1)}M`
}

export function fmtWAR(v: number, signed = false): string {
  const sign = signed && v >= 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}W`
}

/** Minimal Gaussian posterior: the V3 model is linear-Gaussian, so mean + sd
 *  reconstruct the predictive density exactly; p05/p95 give the 90% band. */
export type CurvePosterior = {
  mean: number
  sd: number
  p05: number
  p95: number
}

/** Faithful posterior curve. Renders Normal(mean, sd) with the 90% interval and,
 *  when known, the realized outcome marked in green. No hand-tuning — every number
 *  comes from the model. Shared by the Model route and the Trade Workspace. */
export function PosteriorCurve({
  post,
  realized,
  width = 460,
  height = 150,
  formatter = fmtM,
}: {
  post: CurvePosterior
  realized: number | null
  width?: number
  height?: number
  formatter?: (v: number, signed?: boolean) => string
}) {
  const padX = 8
  const anchor = realized ?? post.mean
  const loDomain = Math.min(post.p05, anchor) - post.sd * 0.6
  const hiDomain = Math.max(post.p95, anchor) + post.sd * 0.6
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

  const realizedInView = realized != null && realized >= loDomain && realized <= hiDomain

  return (
    <svg width={width} height={height} className="block w-full" viewBox={`0 0 ${width} ${height}`}>
      {loDomain < 0 && hiDomain > 0 ? (
        <line x1={x(0)} x2={x(0)} y1={10} y2={baseY} stroke="rgba(138,150,192,0.3)" strokeDasharray="2 3" />
      ) : null}
      <rect
        x={x(post.p05)}
        y={baseY + 6}
        width={Math.max(0, x(post.p95) - x(post.p05))}
        height={4}
        rx={2}
        fill="rgba(255,138,61,0.55)"
      />
      <path d={area} fill="rgba(255,138,61,0.16)" stroke="rgba(255,138,61,0.9)" strokeWidth={1.3} />
      <line x1={x(post.mean)} x2={x(post.mean)} y1={baseY - yScale(yMax)} y2={baseY} stroke="rgba(255,138,61,0.95)" strokeWidth={1.4} />
      <circle cx={x(post.mean)} cy={baseY - yScale(yMax)} r={3.4} fill="#ff8a3d" stroke="#0b1018" strokeWidth={1.4} />
      {realizedInView ? (
        <g>
          <line x1={x(realized)} x2={x(realized)} y1={8} y2={baseY} stroke="#3ddc97" strokeWidth={2} />
          <text x={x(realized)} y={6} fontSize={10} textAnchor="middle" fill="#3ddc97" fontFamily="JetBrains Mono">
            realized {formatter(realized)}
          </text>
        </g>
      ) : null}
      {[post.p05, post.mean, post.p95].map((v, i) => (
        <text key={i} x={x(v)} y={height - 8} fontSize={9} textAnchor="middle" fill="rgba(138,150,192,0.8)" fontFamily="JetBrains Mono">
          {formatter(v)}
        </text>
      ))}
    </svg>
  )
}
