import { scaleLinear } from 'd3-scale'
import { featureLabel, type CredibleFeature } from '../lib/modelPosteriors'

const LABEL_W = 210
const CHART_W = 240
const ANNOT_W = 54
const TOTAL_W = LABEL_W + CHART_W + ANNOT_W

const BAR_H = 20
const ROW_GAP = 8

const BUCKET_LABELS: Record<string, string> = {
  receiver_acquired_player_quality: 'player',
  receiver_acquired_pct_awarded: 'player',
  receiver_acquired_pitcher_arsenal_volatility: 'player',
  receiver_acquired_milb_age_advantage: 'player',
  receiver_acquired_from_dev_cluster_score: 'player',
  receiver_acquired_pitcher_k_trajectory: 'player',
  receiver_acquired_milb_hit_quality: 'player',
  receiver_acquired_player_avg_war_trajectory: 'player',
  receiver_pct_pitchers: 'player',
  receiver_avg_age_at_trade: 'player',
  receiver_dev_fit_hitting: 'team',
  receiver_dev_fit_pitching: 'team',
  receiver_org_pitcher_k_jump_3yr: 'team',
  receiver_org_hitter_xwoba_jump_3yr: 'team',
  receiver_total_payroll: 'team',
  receiver_tech_adoption_lead_years: 'team',
  receiver_alumni_network_score: 'team',
  receiver_platoon_woba_diff: 'team',
}

function shortLabel(feature: string): string {
  const full = featureLabel(feature)
  return full.length > 34 ? full.slice(0, 32) + '…' : full
}

export function FeatureBetaChart({ features }: { features: CredibleFeature[] }) {
  const sorted = [...features].sort((a, b) => b.directional_mass - a.directional_mass)

  const maxAbs = Math.max(...sorted.map((f) => Math.abs(f.beta))) * 1.15
  const x = scaleLinear().domain([-maxAbs, maxAbs]).range([0, CHART_W])
  const zeroX = x(0)

  const playerFeatures = sorted.filter((f) => BUCKET_LABELS[f.feature] !== 'team')
  const teamFeatures = sorted.filter((f) => BUCKET_LABELS[f.feature] === 'team')

  function renderGroup(group: CredibleFeature[], yOffset: number) {
    return group.map((f, i) => {
      const ry = yOffset + i * (BAR_H + ROW_GAP)
      const isPos = f.beta >= 0
      const bx = isPos ? zeroX : x(f.beta)
      const bw = Math.max(2, Math.abs(x(f.beta) - zeroX))
      const fill = isPos ? 'rgba(61,220,151,0.5)' : 'rgba(255,93,115,0.5)'
      const stroke = isPos ? 'rgba(61,220,151,0.85)' : 'rgba(255,93,115,0.8)'

      return (
        <g key={f.feature} transform={`translate(0,${ry})`}>
          {/* Feature name */}
          <text
            x={LABEL_W - 8}
            y={BAR_H / 2}
            textAnchor="end"
            fontSize={10.5}
            fill="rgba(185,193,222,0.88)"
            dominantBaseline="middle"
            fontFamily="system-ui, sans-serif"
          >
            {shortLabel(f.feature)}
          </text>
          {/* Zero line segment */}
          <line
            x1={LABEL_W + zeroX}
            x2={LABEL_W + zeroX}
            y1={0}
            y2={BAR_H}
            stroke="rgba(138,150,192,0.2)"
          />
          {/* Beta bar */}
          <rect
            x={LABEL_W + bx}
            y={2}
            width={bw}
            height={BAR_H - 4}
            fill={fill}
            stroke={stroke}
            strokeWidth={0.8}
            rx={2}
          />
          {/* Confidence annotation */}
          <text
            x={LABEL_W + CHART_W + 8}
            y={BAR_H / 2}
            fontSize={9.5}
            fill="rgba(90,104,150,0.9)"
            dominantBaseline="middle"
            fontFamily="JetBrains Mono, monospace"
          >
            {(f.directional_mass * 100).toFixed(0)}%
          </text>
        </g>
      )
    })
  }

  const playerH = playerFeatures.length * (BAR_H + ROW_GAP)
  const teamH = teamFeatures.length * (BAR_H + ROW_GAP)
  const headerH = 18
  const groupGap = 20
  const totalH = headerH + playerH + groupGap + headerH + teamH + 24

  return (
    <svg width={TOTAL_W} height={totalH} className="w-full" viewBox={`0 0 ${TOTAL_W} ${totalH}`}>
      {/* Column header */}
      <text x={LABEL_W + zeroX} y={10} textAnchor="middle" fontSize={9} fill="rgba(138,150,192,0.45)" fontFamily="JetBrains Mono, monospace">
        ← lowers · raises →
      </text>
      <text x={LABEL_W + CHART_W + 8} y={10} fontSize={9} fill="rgba(138,150,192,0.45)" fontFamily="JetBrains Mono, monospace">
        confidence
      </text>

      {/* Player / acquired bucket */}
      <text x={0} y={headerH + 4} fontSize={9} fontWeight="600" fill="rgba(255,138,61,0.7)" letterSpacing="0.12em" fontFamily="system-ui, sans-serif">
        ACQUIRED PLAYER
      </text>
      <g transform={`translate(0,${headerH + 8})`}>
        {renderGroup(playerFeatures, 0)}
      </g>

      {/* Receiving team bucket */}
      {teamFeatures.length > 0 && (
        <>
          <text x={0} y={headerH + 8 + playerH + groupGap} fontSize={9} fontWeight="600" fill="rgba(90,104,150,0.85)" letterSpacing="0.12em" fontFamily="system-ui, sans-serif">
            RECEIVING TEAM
          </text>
          <g transform={`translate(0,${headerH + 8 + playerH + groupGap + 8})`}>
            {renderGroup(teamFeatures, 0)}
          </g>
        </>
      )}

      {/* Legend */}
      <g transform={`translate(${LABEL_W + 4},${totalH - 12})`}>
        <rect x={0} y={-5} width={8} height={8} fill="rgba(61,220,151,0.5)" stroke="rgba(61,220,151,0.85)" strokeWidth={0.7} rx={1} />
        <text x={12} y={0} fontSize={9} fill="rgba(138,150,192,0.6)" dominantBaseline="middle" fontFamily="JetBrains Mono, monospace">raises trade value</text>
        <rect x={120} y={-5} width={8} height={8} fill="rgba(255,93,115,0.5)" stroke="rgba(255,93,115,0.8)" strokeWidth={0.7} rx={1} />
        <text x={132} y={0} fontSize={9} fill="rgba(138,150,192,0.6)" dominantBaseline="middle" fontFamily="JetBrains Mono, monospace">lowers trade value</text>
      </g>
    </svg>
  )
}
