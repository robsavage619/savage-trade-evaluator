import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Copy, ClipboardCheck, Terminal, Sparkles, RotateCcw, AlertCircle, CheckCircle2 } from 'lucide-react'
import type { TradeBundle } from '../types'
import type { PipelineEntry } from '../data/pipeline'
import { composeClaudePrompt } from '../lib/composePrompt'
import { parseReasoningResponse, useReasoningStore } from '../lib/reasoningStore'

type Props = {
  open: boolean
  onClose: () => void
  trade: TradeBundle
  pipeline: PipelineEntry
}

type Step = 1 | 2 | 3

export function ClaudeCodeDrawer({ open, onClose, trade, pipeline }: Props) {
  const [step, setStep] = useState<Step>(1)
  const [response, setResponse] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const setReasoning = useReasoningStore((s) => s.set)
  const clearReasoning = useReasoningStore((s) => s.clear)
  const hasOverride = useReasoningStore((s) => Boolean(s.overrides[pipeline.tradeId]))
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)

  const prompt = composeClaudePrompt(trade, pipeline)

  useEffect(() => {
    if (!open) {
      setStep(1)
      setResponse('')
      setError(null)
      setCopied(false)
    }
  }, [open, pipeline.tradeId])

  useEffect(() => {
    if (open) {
      const onKey = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose()
      }
      window.addEventListener('keydown', onKey)
      return () => window.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  async function copyPrompt() {
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
    setStep(2)
  }

  function tryApply() {
    setError(null)
    const result = parseReasoningResponse(response)
    if ('error' in result) {
      setError(result.error)
      return
    }
    setReasoning(pipeline.tradeId, result)
    setStep(3)
  }

  function resetDefaults() {
    clearReasoning(pipeline.tradeId)
    setResponse('')
    setStep(1)
    setError(null)
  }

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={onClose}
          />
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 32 }}
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-ink-700 bg-ink-900 shadow-[0_0_120px_rgba(0,0,0,0.6)]"
          >
            <header className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400">
                  <Terminal className="h-4 w-4" strokeWidth={2.4} />
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Reason with Claude Code</div>
                  <div className="text-[14px] font-semibold tracking-tight text-ink-100">{pipeline.shortLabel}</div>
                </div>
              </div>
              <button onClick={onClose} className="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-ink-800 hover:text-ink-100">
                <X className="h-4 w-4" />
              </button>
            </header>

            {/* Stepper */}
            <div className="flex items-center gap-2 border-b border-ink-700 bg-ink-900/80 px-5 py-2.5">
              {([
                { n: 1, label: 'Copy prompt' },
                { n: 2, label: 'Paste in Claude Code' },
                { n: 3, label: 'Paste JSON back' },
              ] as const).map((s) => (
                <div key={s.n} className="flex items-center gap-2">
                  <div
                    className={`mono grid h-5 w-5 place-items-center rounded-full text-[10px] font-bold ${
                      step >= s.n ? 'bg-accent-500 text-ink-950' : 'bg-ink-700 text-ink-300'
                    }`}
                  >
                    {s.n}
                  </div>
                  <div className={`text-[11px] ${step >= s.n ? 'text-ink-100' : 'text-ink-400'}`}>{s.label}</div>
                  {s.n < 3 && <div className={`mx-2 h-px w-6 ${step > s.n ? 'bg-accent-500' : 'bg-ink-700'}`} />}
                </div>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {/* Step 1: prompt */}
              <section className="mb-6">
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 1 · Generated prompt</div>
                    <div className="text-[13px] text-ink-200">
                      Bundles trade legs, WAR windows, Statcast arsenal, personnel, naive baseline, and the receiving-team context features.
                    </div>
                  </div>
                  <button
                    onClick={copyPrompt}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 transition-colors hover:bg-accent-400"
                  >
                    {copied ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    {copied ? 'Copied' : 'Copy prompt'}
                  </button>
                </div>
                <pre className="max-h-72 overflow-y-auto rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[11px] leading-relaxed text-ink-300 mono whitespace-pre-wrap">
                  {prompt}
                </pre>
              </section>

              {/* Step 2: how-to */}
              <section className="mb-6 rounded-md border border-ink-700 bg-ink-800/50 p-4">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">
                  <Sparkles className="h-3 w-3" />
                  Step 2 · In Claude Code
                </div>
                <ol className="ml-4 list-decimal space-y-1 text-[12px] leading-relaxed text-ink-200 marker:text-ink-500">
                  <li>Paste the prompt into Claude Code chat</li>
                  <li>Claude returns a single fenced <code className="mono rounded bg-ink-700 px-1 text-[10.5px]">```json</code> block</li>
                  <li>Copy that JSON block (including or excluding the fences — both work)</li>
                  <li>Paste into Step 3 below</li>
                </ol>
              </section>

              {/* Step 3: response */}
              <section>
                <div className="mb-2 flex items-center justify-between">
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 3 · Paste Claude&apos;s response</div>
                    <div className="text-[13px] text-ink-200">JSON only — fences OK. Validates against the AiReasoning schema.</div>
                  </div>
                  {hasOverride && (
                    <button
                      onClick={resetDefaults}
                      className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1 text-[11px] text-ink-300 transition-colors hover:border-negative-500/50 hover:text-negative-500"
                    >
                      <RotateCcw className="h-3 w-3" /> Reset to default
                    </button>
                  )}
                </div>
                <textarea
                  ref={textareaRef}
                  value={response}
                  onChange={(e) => setResponse(e.target.value)}
                  placeholder='```json
{
  "headline": "...",
  "thesis": "...",
  "keyDrivers": [...],
  "watchOuts": [...],
  "recommendation": "...",
  "citations": [...],
  "modelMeta": { "model": "claude-opus-4-7", "contextWindow": "1M", "latencyMs": 0, "promptTokens": 0, "outputTokens": 0 }
}
```'
                  rows={12}
                  className="mono w-full rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[12px] leading-relaxed text-ink-200 placeholder:text-ink-500 focus:border-accent-500/50 focus:outline-none"
                  spellCheck={false}
                />
                {error && (
                  <div className="mt-2 flex items-start gap-2 rounded-md border border-negative-500/40 bg-negative-500/10 px-3 py-2 text-[12px] text-negative-500">
                    <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}
                {step === 3 && !error && (
                  <div className="mt-2 flex items-center gap-2 rounded-md border border-positive-500/40 bg-positive-500/10 px-3 py-2 text-[12px] text-positive-500">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    Applied. The Reasoning panel now renders Claude&apos;s analysis.
                  </div>
                )}
                <div className="mt-3 flex items-center justify-end gap-2">
                  <button
                    onClick={onClose}
                    className="rounded-md border border-ink-700 px-3 py-1.5 text-[12px] text-ink-300 transition-colors hover:border-ink-500 hover:text-ink-100"
                  >
                    Done
                  </button>
                  <button
                    onClick={tryApply}
                    disabled={!response.trim()}
                    className="rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-500"
                  >
                    Parse &amp; apply
                  </button>
                </div>
              </section>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
