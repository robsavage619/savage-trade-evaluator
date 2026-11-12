import { useMemo } from 'react'
import { histogram, summarize, type Atoms } from '../lib/structural'

/** Probability mass of the net captured-WAR forecast, with the exact-zero case in the
 *  middle bar. Drawn from the model's own distribution, not a fitted normal curve. */
export function ForecastDistribution({
  atoms, width = 420, height = 70,
}: { atoms: Atoms; width?: number; height?: number }) {
  const bins = 41
  const { bars, half, mean } = useMemo(() => {
    const s = summarize(atoms)
    // Twice the 90% band, so the tail folded into the end bins is a sliver, not a bump.
    const half = Math.max(Math.abs(s.p5), Math.abs(s.p95), 1) * 2
    return { bars: histogram(atoms, -half, half, bins), half, mean: s.mean }
  }, [atoms])
  const top = Math.max(...bars, 1e-9)
  const w = width / bins
  const x = (v: number) => ((v + half) / (2 * half)) * width
  const base = height - 14
  return (
    <svg width={width} height={height} role="img" aria-label="Distribution of net captured WAR">
      {bars.map((m, i) => {
        const h = (m / top) * (base - 4)
        const center = i === (bins - 1) / 2
        const positive = i > (bins - 1) / 2
        return (
          <rect
            key={i}
            x={i * w + 0.5}
            y={base - h}
            width={w - 1}
            height={h}
            fill={center ? 'rgba(160,160,170,0.55)' : positive ? 'rgba(61,220,151,0.55)' : 'rgba(255,93,115,0.5)'}
          />
        )
      })}
      <line x1={x(0)} x2={x(0)} y1={2} y2={base} stroke="rgba(200,200,210,0.5)" strokeDasharray="2 2" />
      <line x1={x(mean)} x2={x(mean)} y1={2} y2={base} stroke="rgba(255,138,61,0.95)" strokeWidth={1.5} />
      <text x={0} y={height - 2} fontSize={9} fill="currentColor" className="text-ink-500">{(-half).toFixed(0)}</text>
      <text x={width / 2} y={height - 2} fontSize={9} textAnchor="middle" fill="currentColor" className="text-ink-500">net WAR · bar at 0 = no difference</text>
      <text x={width} y={height - 2} fontSize={9} textAnchor="end" fill="currentColor" className="text-ink-500">+{half.toFixed(0)}</text>
    </svg>
  )
}
