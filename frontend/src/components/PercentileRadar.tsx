import { useMemo } from 'react'

type Metric = { label: string; value: number | null }

/** Compact polar radar of Statcast percentile ranks (0-100). Uses native SVG. */
export function PercentileRadar({ metrics, size = 280, accent = '#ff6a13' }: { metrics: Metric[]; size?: number; accent?: string }) {
  const cx = size / 2
  const cy = size / 2
  const radius = size / 2 - 30
  const n = metrics.length
  const points = useMemo(() => {
    return metrics.map((m, i) => {
      const angle = (Math.PI * 2 * i) / n - Math.PI / 2
      const r = ((m.value ?? 0) / 100) * radius
      return {
        ...m,
        angle,
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
        labelX: cx + (radius + 14) * Math.cos(angle),
        labelY: cy + (radius + 14) * Math.sin(angle),
      }
    })
  }, [metrics, n, cx, cy, radius])

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ') + ' Z'

  const rings = [25, 50, 75, 100]

  return (
    <svg width={size} height={size} className="block">
      {/* Rings */}
      {rings.map((r) => (
        <circle key={r} cx={cx} cy={cy} r={(r / 100) * radius} fill="none" stroke="rgba(138,150,192,0.12)" strokeWidth={1} />
      ))}
      {/* Spokes */}
      {points.map((p, i) => (
        <line
          key={`spoke-${i}`}
          x1={cx}
          y1={cy}
          x2={cx + radius * Math.cos(p.angle)}
          y2={cy + radius * Math.sin(p.angle)}
          stroke="rgba(138,150,192,0.1)"
        />
      ))}
      {/* Filled polygon */}
      <path d={path} fill={accent} fillOpacity={0.18} stroke={accent} strokeWidth={1.5} />
      {/* Dots */}
      {points.map((p, i) =>
        p.value == null ? null : (
          <g key={`dot-${i}`}>
            <circle cx={p.x} cy={p.y} r={2.5} fill={accent} stroke="#0b1018" strokeWidth={1} />
          </g>
        ),
      )}
      {/* Labels */}
      {points.map((p, i) => (
        <g key={`lbl-${i}`}>
          <text
            x={p.labelX}
            y={p.labelY}
            fontSize={9.5}
            fontFamily="JetBrains Mono"
            fill="#b9c1de"
            textAnchor={Math.cos(p.angle) > 0.2 ? 'start' : Math.cos(p.angle) < -0.2 ? 'end' : 'middle'}
            dominantBaseline={Math.sin(p.angle) > 0.2 ? 'hanging' : Math.sin(p.angle) < -0.2 ? 'auto' : 'middle'}
          >
            {p.label}
          </text>
          {p.value != null ? (
            <text
              x={p.labelX}
              y={p.labelY + (Math.sin(p.angle) > 0.2 ? 12 : -10)}
              fontSize={10}
              fontFamily="JetBrains Mono"
              fontWeight={600}
              fill={p.value >= 67 ? '#3ddc97' : p.value >= 34 ? '#b9c1de' : '#ff5d73'}
              textAnchor={Math.cos(p.angle) > 0.2 ? 'start' : Math.cos(p.angle) < -0.2 ? 'end' : 'middle'}
            >
              {p.value.toFixed(0)}
            </text>
          ) : null}
        </g>
      ))}
      {/* Center label */}
      <text x={cx} y={cy - 6} fontSize={10} fontFamily="JetBrains Mono" fill="#5a6896" textAnchor="middle">pctile</text>
      <text x={cx} y={cy + 6} fontSize={10} fontFamily="JetBrains Mono" fill="#5a6896" textAnchor="middle">vs MLB</text>
    </svg>
  )
}
