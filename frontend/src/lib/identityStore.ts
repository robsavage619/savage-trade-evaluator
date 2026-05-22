import { create } from 'zustand'
import { persist } from 'zustand/middleware'

type IdentityState = {
  activeTeam: string // bref
  setActiveTeam: (bref: string) => void
}

export const useIdentityStore = create<IdentityState>()(
  persist(
    (set) => ({
      activeTeam: 'NYM',
      setActiveTeam: (bref) => set({ activeTeam: bref }),
    }),
    { name: 'ste-identity-v1' },
  ),
)

/** Approximate team primary/secondary colors for theming. Used for accent overrides. */
export const TEAM_THEME: Record<string, { primary: string; secondary: string }> = {
  ARI: { primary: '#A71930', secondary: '#E3D4AD' },
  ATL: { primary: '#CE1141', secondary: '#13274F' },
  BAL: { primary: '#DF4601', secondary: '#000000' },
  BOS: { primary: '#BD3039', secondary: '#0C2340' },
  CHC: { primary: '#0E3386', secondary: '#CC3433' },
  CHW: { primary: '#27251F', secondary: '#C4CED4' },
  CIN: { primary: '#C6011F', secondary: '#000000' },
  CLE: { primary: '#00385D', secondary: '#E50022' },
  COL: { primary: '#333366', secondary: '#C4CED4' },
  DET: { primary: '#0C2340', secondary: '#FA4616' },
  HOU: { primary: '#EB6E1F', secondary: '#002D62' },
  KCR: { primary: '#004687', secondary: '#BD9B60' },
  LAA: { primary: '#BA0021', secondary: '#003263' },
  LAD: { primary: '#005A9C', secondary: '#EF3E42' },
  MIA: { primary: '#00A3E0', secondary: '#EF3340' },
  MIL: { primary: '#FFC52F', secondary: '#12284B' },
  MIN: { primary: '#002B5C', secondary: '#D31145' },
  NYM: { primary: '#FF5910', secondary: '#002D72' },
  NYY: { primary: '#0C2340', secondary: '#C4CED4' },
  OAK: { primary: '#003831', secondary: '#EFB21E' },
  PHI: { primary: '#E81828', secondary: '#002D72' },
  PIT: { primary: '#FDB827', secondary: '#27251F' },
  SDP: { primary: '#2F241D', secondary: '#FFC425' },
  SEA: { primary: '#0C2C56', secondary: '#005C5C' },
  SFG: { primary: '#FD5A1E', secondary: '#27251F' },
  STL: { primary: '#C41E3A', secondary: '#0C2340' },
  TBR: { primary: '#092C5C', secondary: '#8FBCE6' },
  TEX: { primary: '#003278', secondary: '#C0111F' },
  TOR: { primary: '#134A8E', secondary: '#E8291C' },
  WSN: { primary: '#AB0003', secondary: '#14225A' },
}
