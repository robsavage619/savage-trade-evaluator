import { scaleLinear } from 'd3-scale'

type Props = {
  values: Array<number | null>
  width?: number
  height?: number
  highlightIndex?: number | null
  accent?: string
}

export function Sparkline({ values, width = 110, height = 28, highlightIndex, accent = 'var(--color-accent-400)' }: Props) {
  const cleaned = values.map((v) => (typeof v === 'number' ? v : null))
  const numeric = cleaned.filter((v): v is number => v !== null)
  if (numeric.length === 0) return <div style={{ width, height }} />
  const yMin = Math.min(...numeric, 0)
  const yMax = Math.max(...numeric, 0)
  const x = scaleLinear().domain([0, cleaned.length - 1]).range([2, width - 2])
  const y = scaleLinear().domain([yMin, yMax]).range([height - 2, 2])
  const path = cleaned
    .map((v, i) => (v === null ? '' : `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(2)} ${y(v).toFixed(2)}`))
    .filter(Boolean)
    .join(' ')
  return (
    <svg width={width} height={height} className="block">
      {yMin < 0 && yMax > 0 ? (
        <line x1={0} x2={width} y1={y(0)} y2={y(0)} stroke="rgba(138,150,192,0.25)" strokeDasharray="2 3" />
      ) : null}
      <path d={path} fill="none" stroke={accent} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
      {cleaned.map((v, i) =>
        v === null ? null : (
          <circle
            key={i}
            cx={x(i)}
            cy={y(v)}
            r={i === highlightIndex ? 2.6 : 1.5}
            fill={i === highlightIndex ? accent : 'rgba(224,229,244,0.55)'}
          />
        ),
      )}
    </svg>
  )
}
