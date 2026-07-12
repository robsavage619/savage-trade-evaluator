import type { GmContext as GmContextType } from '../../data/warroom/types'
import { Cite, SectionHeader } from './primitives'

const GM_CITE = {
  label: 'GM Archetype',
  detail: 'Behavioral profile derived from 2010–2024 trade history. Archetype clustering on: WAR buyer bias, avg player age at acquisition, deadline concentration, pitching focus, and trade volume. 86 regimes, 5 archetypes.',
}

const ACCEPT_CITE = {
  label: 'P(accept)',
  detail: 'Logistic regression trained on MLBTR rumor weak labels (rumored player+team pair matched to a real transaction within 90 days = accepted). Features: this GM\'s war_buyer_bias, avg_age_received, deadline_pct, archetype cluster. Diagnostic prior, not a hard gate.',
}

function StatChip({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">{label}</div>
      <div className="font-mono text-[13px] font-bold tabular text-ink-100">{value}</div>
      {sub && <div className="font-mono text-[9px] text-ink-500">{sub}</div>}
    </div>
  )
}

export function GmContext({ gmContext }: { gmContext?: GmContextType }) {
  if (!gmContext) return null

  const biasLabel = gmContext.warBuyerBias > 0.1 ? 'WAR buyer' : gmContext.warBuyerBias < -0.1 ? 'WAR seller' : 'balanced'
  const biasColor = gmContext.warBuyerBias > 0.1 ? 'text-positive-400' : gmContext.warBuyerBias < -0.1 ? 'text-negative-400' : 'text-ink-400'

  return (
    <div className="space-y-3">
      <SectionHeader label="Front Office Context" cite={GM_CITE} />

      <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-4">
        {/* GM name + archetype */}
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500 mb-0.5">
              Decision Maker
            </div>
            <div className="text-[14px] font-semibold text-ink-100">{gmContext.name}</div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-accent-400 mb-0.5">
              Archetype
            </div>
            <div className="font-mono text-[12px] font-bold text-ink-100">{gmContext.archetype}</div>
          </div>
        </div>

        {/* Archetype description */}
        <p className="mb-4 text-[11px] leading-relaxed text-ink-400">
          {gmContext.archetypeDescription}
        </p>

        {/* Stat grid */}
        <div className={`grid grid-cols-2 gap-x-6 gap-y-3 ${gmContext.pAccept != null ? 'sm:grid-cols-5' : 'sm:grid-cols-4'}`}>
          <StatChip
            label="Trade bias"
            value={biasLabel.charAt(0).toUpperCase() + biasLabel.slice(1)}
            sub={`bias score ${gmContext.warBuyerBias > 0 ? '+' : ''}${gmContext.warBuyerBias.toFixed(2)}`}
          />
          <StatChip
            label="Avg age acquired"
            value={gmContext.avgAgeReceived.toFixed(1)}
            sub="years at trade"
          />
          <StatChip
            label="Deadline %"
            value={`${gmContext.deadlinePct.toFixed(0)}%`}
            sub="trades at deadline"
          />
          <StatChip
            label="Trade volume"
            value={`${gmContext.tradesPerSeason.toFixed(1)}`}
            sub={`trades/season · ${gmContext.nTrades} total`}
          />
          {gmContext.pAccept != null && (
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-1">
                <div className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-500">
                  P(accept)
                </div>
                <Cite cite={ACCEPT_CITE} />
              </div>
              <div className={`font-mono text-[13px] font-bold tabular ${gmContext.pAccept >= 0.5 ? 'text-positive-400' : 'text-negative-400'}`}>
                {(gmContext.pAccept * 100).toFixed(0)}%
              </div>
              <div className="font-mono text-[9px] text-ink-500">rumor-outcome model</div>
            </div>
          )}
        </div>

        {/* Bias color bar */}
        <div className="mt-4 flex items-center gap-2">
          <span className="font-mono text-[9px] text-ink-600">seller</span>
          <div className="relative h-1.5 flex-1 rounded-full bg-ink-800">
            <div
              className={`absolute top-0 h-1.5 w-1.5 rounded-full ${biasColor.replace('text-', 'bg-')}`}
              style={{ left: `${Math.max(2, Math.min(98, (gmContext.warBuyerBias + 1) * 50))}%`, transform: 'translateX(-50%)' }}
            />
          </div>
          <span className="font-mono text-[9px] text-ink-600">buyer</span>
        </div>
      </div>
    </div>
  )
}
