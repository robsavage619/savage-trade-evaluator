import { scaleLinear } from 'd3-scale'
import type { ComparisonFold } from '../lib/modelPosteriors'

const W = 560
const H = 200
const PAD = { top: 12, right: 16, bottom: 44, left: 40 }

const TIERS = [
  { key: 'crps_intercept' as const, label: 'Predict the mean', fill: 'rgba(138,150,192,0.28)', stroke: 'rgba(138,150,192,0.5)' },
  { key: 'crps_quality' as const, label: 'Player quality only', fill: 'rgba(90,104,150,0.55)', stroke: 'rgba(90,104,150,0.85)' },
  { key: 'crps_context' as const, label: 'Context-aware (V3)', fill: 'rgba(255,138,61,0.75)', stroke: 'rgba(255,138,61,0.95)' },
]

export function FoldCrpsChart({ folds }: { folds: ComparisonFold[] }) {
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom

  const maxCrps = Math.max(...folds.flatMap((f) => [f.crps_context, f.crps_quality, f.crps_intercept]))
  const y = scaleLinear().domain([0, maxCrps * 1.15]).range([plotH, 0]).nice()

  const groupW = plotW / folds.length
  const barPad = 2.5
  const barW = (groupW - barPad * 4) / 3

  const yticks = y.ticks(4)

  return (
    <div>
      <svg width={W} height={H} className="w-full" viewBox={`0 0 ${W} ${H}`}>
        {/* Y-axis grid + ticks */}
        {yticks.map((t) => (
          <g key={t} transform={`translate(${PAD.left},${PAD.top + y(t)})`}>
            <line x1={0} x2={plotW} stroke="rgba(138,150,192,0.10)" />
            <text x={-5} dy="0.33em" textAnchor="end" fontSize={9} fill="rgba(138,150,192,0.55)" fontFamily="JetBrains Mono, monospace">
              {t.toFixed(1)}W
            </text>
          </g>
        ))}

        {/* Bar groups */}
        {folds.map((f, gi) => {
          const gx = PAD.left + gi * groupW
          return (
            <g key={f.label} transform={`translate(${gx},${PAD.top})`}>
              {f.structural_break && (
                <rect x={1} y={0} width={groupW - 2} height={plotH} fill="rgba(245,165,36,0.05)" />
              )}
              {TIERS.map((tier, bi) => {
                const bx = barPad + bi * (barW + barPad)
                const val = f[tier.key] as number
                const bh = plotH - y(val)
                return (
                  <rect
                    key={tier.key}
                    x={bx}
                    y={y(val)}
                    width={barW}
                    height={bh}
                    fill={tier.fill}
                    stroke={tier.stroke}
                    strokeWidth={0.6}
                    rx={1.5}
                  />
                )
              })}
              {/* Fold label */}
              <text x={groupW / 2} y={plotH + 10} textAnchor="middle" fontSize={9} fill="rgba(138,150,192,0.65)" fontFamily="JetBrains Mono, monospace">
                {f.label}
              </text>
              {f.structural_break && (
                <text x={groupW / 2} y={plotH + 22} textAnchor="middle" fontSize={8} fill="rgba(245,165,36,0.75)">
                  structural break
                </text>
              )}
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-[10px] text-ink-400">
        {TIERS.map((t) => (
          <span key={t.key} className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-3 rounded-sm" style={{ background: t.fill, border: `1px solid ${t.stroke}` }} />
            {t.label}
          </span>
        ))}
        <span className="flex items-center gap-1.5 ml-2">
          <span className="inline-block h-2.5 w-3 rounded-sm" style={{ background: 'rgba(245,165,36,0.12)', border: '1px solid rgba(245,165,36,0.4)' }} />
          structural break fold (excluded from averages)
        </span>
      </div>
    </div>
  )
}
