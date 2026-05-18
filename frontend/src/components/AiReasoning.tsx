import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Brain, Sparkles, Zap, AlertTriangle, ChevronRight, RotateCcw, BookOpen, Terminal, Wand2 } from 'lucide-react'
import type { AiReasoning as AiReasoningType } from '../data/pipeline'

type Props = {
  reasoning: AiReasoningType
  /** key changes (e.g. tradeId) reset the panel to idle */
  resetKey: string | number
  /** auto-start streaming when component mounts (default true) */
  autoRun?: boolean
  /** When set, renders the "Reason with Claude Code" CTA. */
  onOpenClaude?: () => void
  /** Set when reasoning came from a Claude Code paste (renders a badge). */
  sourceLabel?: string
  savedAt?: string
}

type Phase = 'idle' | 'thinking' | 'streaming' | 'done'

export function AiReasoning({ reasoning, resetKey, autoRun = true, onOpenClaude, sourceLabel, savedAt }: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [streamed, setStreamed] = useState('')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Compose a markdown-like full body to stream
  const fullBody = composeBody(reasoning)

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setPhase('idle')
    setStreamed('')
    if (autoRun) {
      const t = setTimeout(() => start(), 350)
      return () => clearTimeout(t)
    }
  }, [resetKey, autoRun])

  function start() {
    if (timerRef.current) clearTimeout(timerRef.current)
    setPhase('thinking')
    setStreamed('')
    timerRef.current = setTimeout(() => stream(0), 900)
  }

  function stream(i: number) {
    if (i >= fullBody.length) {
      setPhase('done')
      return
    }
    setPhase('streaming')
    const stepSize = Math.max(2, Math.min(6, Math.round(fullBody.length / 320)))
    setStreamed(fullBody.slice(0, i + stepSize))
    timerRef.current = setTimeout(() => stream(i + stepSize), 14)
  }

  return (
    <div className="card relative overflow-hidden">
      <div className="absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r from-accent-500 via-baseline-500 to-positive-500 opacity-70" aria-hidden />
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-700 px-5 py-3">
        <div className="flex items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400">
            <Brain className="h-4 w-4" strokeWidth={2.2} />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">AI Reasoning</div>
              {sourceLabel ? (
                <span className="chip chip-pos mono">
                  <Wand2 className="h-2.5 w-2.5" /> live · {sourceLabel}
                </span>
              ) : null}
            </div>
            <div className="text-[14px] font-semibold tracking-tight text-ink-100">
              Context-aware trade analysis
              {savedAt ? (
                <span className="ml-2 text-[11px] font-normal text-ink-400">
                  · saved {new Date(savedAt).toLocaleString()}
                </span>
              ) : null}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="chip mono text-ink-300">
            <Sparkles className="h-2.5 w-2.5" /> {reasoning.modelMeta.model}
          </span>
          <span className="chip mono text-ink-400">{reasoning.modelMeta.contextWindow} ctx</span>
          {phase === 'done' && reasoning.modelMeta.latencyMs > 0 && (
            <span className="chip mono text-ink-400">
              {reasoning.modelMeta.latencyMs}ms · {reasoning.modelMeta.outputTokens} tok
            </span>
          )}
          {onOpenClaude ? (
            <button
              onClick={onOpenClaude}
              className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-2.5 py-1 text-[11px] font-semibold text-ink-950 transition-colors hover:bg-accent-400"
            >
              <Terminal className="h-3 w-3" />
              Reason with Claude Code
            </button>
          ) : null}
          <button
            onClick={start}
            className="ml-1 inline-flex items-center gap-1 rounded-md border border-ink-600 px-2.5 py-1 text-[11px] font-medium text-ink-200 transition-colors hover:border-accent-500/60 hover:text-ink-100"
            disabled={phase === 'streaming' || phase === 'thinking'}
          >
            {phase === 'idle' || phase === 'done' ? (
              <>
                <RotateCcw className="h-3 w-3" /> Re-run
              </>
            ) : (
              <>
                <Zap className="h-3 w-3 animate-pulse text-accent-400" />
                {phase === 'thinking' ? 'Thinking…' : 'Streaming…'}
              </>
            )}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-0 lg:grid-cols-[1fr_280px]">
        <div className="p-5">
          {/* Headline */}
          <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Headline</div>
          <div className="mb-5 text-[15px] font-semibold leading-snug text-ink-100">
            <AnimatePresence mode="wait">
              <motion.span
                key={resetKey + '-headline'}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
              >
                {reasoning.headline}
              </motion.span>
            </AnimatePresence>
          </div>

          {/* Streaming body */}
          <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">
            Reasoning trace
            {(phase === 'streaming' || phase === 'thinking') && (
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-400" />
            )}
          </div>
          <div className="relative min-h-[280px] rounded-md border border-ink-700 bg-ink-900/70 p-4">
            {phase === 'idle' && (
              <button onClick={start} className="text-[12px] text-ink-400 hover:text-ink-200">
                Click <span className="text-accent-400">Re-run</span> to generate reasoning.
              </button>
            )}
            {phase === 'thinking' && <ThinkingDots />}
            {(phase === 'streaming' || phase === 'done') && (
              <MarkdownLike text={streamed} blinking={phase === 'streaming'} />
            )}
          </div>
        </div>

        {/* Side rail: citations + meta */}
        <aside className="border-l border-ink-700 bg-ink-900/40 p-5">
          <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">
            <BookOpen className="h-3 w-3" /> Grounding
          </div>
          <ul className="mb-5 space-y-2 text-[12px]">
            {reasoning.citations.map((c, i) => (
              <li key={i} className="rounded-md border border-ink-700 bg-ink-800/60 px-2.5 py-2">
                <div className="mono text-[11px] font-medium text-accent-300">[{i + 1}] {c.label}</div>
                <div className="mt-1 text-[11px] leading-snug text-ink-300">{c.detail}</div>
              </li>
            ))}
          </ul>

          <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">
            <AlertTriangle className="h-3 w-3" /> Watch-outs
          </div>
          <ul className="space-y-2 text-[11px]">
            {reasoning.watchOuts.map((w, i) => (
              <li key={i} className="flex gap-2 rounded-md bg-negative-500/[0.06] px-2 py-1.5">
                <ChevronRight className="mt-0.5 h-3 w-3 shrink-0 text-negative-500" />
                <div>
                  <div className="font-semibold text-ink-100">{w.title}</div>
                  <div className="mt-0.5 leading-snug text-ink-300">{w.body}</div>
                </div>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </div>
  )
}

function ThinkingDots() {
  return (
    <div className="flex items-center gap-2 text-[12px] text-ink-400">
      <span className="inline-flex gap-1">
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-400 [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-400 [animation-delay:120ms]" />
        <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-400 [animation-delay:240ms]" />
      </span>
      Loading trade context · personnel · arsenal · org dev-signature · prior trades…
    </div>
  )
}

function composeBody(r: AiReasoningType): string {
  const drivers = r.keyDrivers
    .map((d, i) => `**${i + 1}. ${d.title}** ${d.chip ? `[${d.chip}]` : ''}\n${d.body}`)
    .join('\n\n')
  return `## Thesis
${r.thesis}

## Key drivers
${drivers}

## Recommendation
${r.recommendation}`
}

/** Lightweight markdown renderer — headers + bold + paragraphs. Enough for our reasoning shape. */
function MarkdownLike({ text, blinking }: { text: string; blinking: boolean }) {
  const blocks = text.split('\n\n')
  return (
    <div className="space-y-3 text-[13px] leading-relaxed text-ink-200">
      {blocks.map((block, i) => {
        const isLast = i === blocks.length - 1
        if (block.startsWith('## ')) {
          return (
            <div key={i} className="mt-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">
              {block.slice(3)}
              {blinking && isLast ? <Cursor /> : null}
            </div>
          )
        }
        if (block.startsWith('**')) {
          // bold paragraph — first line is title
          const [first, ...rest] = block.split('\n')
          const titleBlock = first.replace(/\*\*/g, '')
          return (
            <div key={i}>
              <div className="text-[12px] font-semibold text-ink-100">{titleBlock}</div>
              {rest.length > 0 && (
                <div className="mt-0.5 text-ink-300">
                  {rest.join(' ')}
                  {blinking && isLast ? <Cursor /> : null}
                </div>
              )}
            </div>
          )
        }
        return (
          <p key={i}>
            {block}
            {blinking && isLast ? <Cursor /> : null}
          </p>
        )
      })}
    </div>
  )
}

function Cursor() {
  return <span className="ml-0.5 inline-block h-3 w-1.5 -mb-0.5 animate-pulse bg-accent-400 align-baseline" />
}
