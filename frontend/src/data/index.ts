import type { TradeBundle, OrgLandscape, GmRegime, KpctPoint } from '../types'
import pressly from './seed/trade_371509.json'
import verlander from './seed/trade_331253.json'
import machado from './seed/trade_369676.json'
import betts from './seed/trade_438093.json'
import scherzer from './seed/trade_508180.json'
import soto from './seed/trade_642337.json'
import goldschmidt from './seed/trade_384506.json'
import orgLandscape from './seed/org_landscape.json'
import gmRegimes from './seed/gm_regimes.json'
import kpct from './seed/kpct_finding.json'

export const PRESSLY_TRADE_ID = 371509

export const tradeBundles: Record<number, TradeBundle> = {
  371509: pressly as unknown as TradeBundle,
  331253: verlander as unknown as TradeBundle,
  369676: machado as unknown as TradeBundle,
  438093: betts as unknown as TradeBundle,
  508180: scherzer as unknown as TradeBundle,
  642337: soto as unknown as TradeBundle,
  384506: goldschmidt as unknown as TradeBundle,
}

export function getTrade(id: number): TradeBundle | undefined {
  return tradeBundles[id]
}

export const orgs = orgLandscape as unknown as OrgLandscape
export const gms = gmRegimes as unknown as GmRegime[]
export const kpctPoints = kpct as unknown as KpctPoint[]
