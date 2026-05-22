export function ageOn(birth: string | null, on: string): number | null {
  if (!birth) return null
  const b = new Date(birth)
  const o = new Date(on)
  let age = o.getFullYear() - b.getFullYear()
  const m = o.getMonth() - b.getMonth()
  if (m < 0 || (m === 0 && o.getDate() < b.getDate())) age--
  return age
}

export function fmtSigned(v: number, digits = 2): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}`
}

export function fmtMoney(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}K`
  return `$${v}`
}

export const TEAM_COLORS: Record<string, { primary: string; soft: string }> = {
  HOU: { primary: '#EB6E1F', soft: 'rgba(235,110,31,0.12)' },
  MIN: { primary: '#D31145', soft: 'rgba(211,17,69,0.12)' },
  NYY: { primary: '#0C2340', soft: 'rgba(12,35,64,0.4)' },
  NYM: { primary: '#FF5910', soft: 'rgba(255,89,16,0.12)' },
  LAD: { primary: '#005A9C', soft: 'rgba(0,90,156,0.12)' },
  SFG: { primary: '#FD5A1E', soft: 'rgba(253,90,30,0.12)' },
  TEX: { primary: '#003278', soft: 'rgba(0,50,120,0.18)' },
  STL: { primary: '#C41E3A', soft: 'rgba(196,30,58,0.12)' },
  CLE: { primary: '#00385D', soft: 'rgba(0,56,93,0.2)' },
  SEA: { primary: '#0C2C56', soft: 'rgba(12,44,86,0.2)' },
  BOS: { primary: '#BD3039', soft: 'rgba(189,48,57,0.12)' },
  CHC: { primary: '#0E3386', soft: 'rgba(14,51,134,0.2)' },
}

export function teamColor(bref: string) {
  return TEAM_COLORS[bref] ?? { primary: '#ff8a3d', soft: 'rgba(255,138,61,0.12)' }
}

export const TEAM_MLB_ID: Record<string, number> = {
  ARI: 109, ATL: 144, BAL: 110, BOS: 111, CHC: 112, CHW: 145, CIN: 113,
  CLE: 114, COL: 115, DET: 116, HOU: 117, KCR: 118, LAA: 108, LAD: 119,
  MIA: 146, MIL: 158, MIN: 142, NYM: 121, NYY: 147, OAK: 133, PHI: 143,
  PIT: 134, SDP: 135, SEA: 136, SFG: 137, STL: 138, TBR: 139, TEX: 140,
  TOR: 141, WSN: 120,
}

export function teamLogoUrl(bref: string): string | null {
  const id = TEAM_MLB_ID[bref]
  if (!id) return null
  return `https://www.mlbstatic.com/team-logos/${id}.svg`
}
