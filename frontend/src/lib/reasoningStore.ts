import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { AiReasoning } from '../data/pipeline'

type StoredReasoning = {
  reasoning: AiReasoning
  /** ISO timestamp the override was saved */
  savedAt: string
  /** Source label — "Claude Code · Opus 4.7" by default */
  source: string
}

type ReasoningState = {
  overrides: Record<number, StoredReasoning>
  set: (tradeId: number, reasoning: AiReasoning, source?: string) => void
  clear: (tradeId: number) => void
}

export const useReasoningStore = create<ReasoningState>()(
  persist(
    (set) => ({
      overrides: {},
      set: (tradeId, reasoning, source = 'Claude Code · Opus 4.7') =>
        set((state) => ({
          overrides: {
            ...state.overrides,
            [tradeId]: { reasoning, savedAt: new Date().toISOString(), source },
          },
        })),
      clear: (tradeId) =>
        set((state) => {
          const next = { ...state.overrides }
          delete next[tradeId]
          return { overrides: next }
        }),
    }),
    { name: 'ste-reasoning-overrides-v1' },
  ),
)

const ALLOWED_KEYS: Array<keyof AiReasoning> = [
  'headline',
  'thesis',
  'keyDrivers',
  'watchOuts',
  'recommendation',
  'citations',
  'modelMeta',
]

/** Strict-enough parser for pasted Claude output. Accepts raw JSON or a
 *  fenced ```json block; returns either a typed AiReasoning or a string error. */
export function parseReasoningResponse(raw: string): AiReasoning | { error: string } {
  const trimmed = raw.trim()
  if (!trimmed) return { error: 'Empty input.' }

  // Extract from fenced block if present
  let jsonText = trimmed
  const fence = /```(?:json)?\s*([\s\S]*?)```/i.exec(trimmed)
  if (fence) jsonText = fence[1].trim()

  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText)
  } catch (e) {
    return { error: `JSON parse failed: ${(e as Error).message}` }
  }

  if (!parsed || typeof parsed !== 'object') return { error: 'Top-level value must be an object.' }
  const obj = parsed as Record<string, unknown>

  for (const k of ALLOWED_KEYS) {
    if (!(k in obj)) return { error: `Missing required field: ${k}` }
  }

  if (typeof obj.headline !== 'string') return { error: 'headline must be a string.' }
  if (typeof obj.thesis !== 'string') return { error: 'thesis must be a string.' }
  if (typeof obj.recommendation !== 'string') return { error: 'recommendation must be a string.' }
  if (!Array.isArray(obj.keyDrivers)) return { error: 'keyDrivers must be an array.' }
  if (!Array.isArray(obj.watchOuts)) return { error: 'watchOuts must be an array.' }
  if (!Array.isArray(obj.citations)) return { error: 'citations must be an array.' }
  if (!obj.modelMeta || typeof obj.modelMeta !== 'object') return { error: 'modelMeta must be an object.' }

  return obj as unknown as AiReasoning
}
