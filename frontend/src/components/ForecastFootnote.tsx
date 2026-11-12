import { structuralAsOf, validationFacts as v } from '../lib/structuralData'

/** The disclosure that goes under every captured-WAR forecast. */
export function ForecastFootnote({ missing = 0, className = '' }: { missing?: number; className?: string }) {
  return (
    <div className={`font-mono text-[9px] leading-relaxed text-ink-400 ${className}`}>
      WAR is gross: salary is shown beside it, not netted out. {structuralAsOf.note || `Priced as of ${structuralAsOf.date}`}.
      {' '}Tested on {v.holdout} trades the model never saw ({v.nSides.toLocaleString()} sides): the 90% band held {v.coverage}% of
      outcomes and beat a constant guess by {v.crpsGain}% on CRPS. Picking the side with the higher forecast won {v.favouredWin}% ±{' '}
      {v.favouredHalf} of {v.favouredTrades} two-sided trades, so read the sign as a lean, not a call. The model does not see
      contract length, options or injuries: a star on a long guaranteed deal is priced like a typical veteran, and a
      rental or opt-out candidate is priced as if he stays. No club context or dev-system effect is included either:
      none has been shown to help.
      {missing > 0 ? ` ${missing} player(s) not in the model export were left out.` : ''}
    </div>
  )
}
