import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Brain, ClipboardCopy, Check, RefreshCw, FileText,
  Settings, KeyRound, Maximize2, Loader2, Wand2, X, Trash2,
} from 'lucide-react'
import { warRoomIndex } from '../../lib/warroomData'
import { buildAnalysisPrompt, parseAnalysisReport, normalizePlayerName } from '../../lib/analysisPrompt'
import type { AnalysisReport, PromptInput } from '../../lib/analysisPrompt'
import { generateBriefRaw } from '../../lib/analysisClient'
import { IntelligenceReport } from '../../components/IntelligenceReport'
import { roster } from '../../data/players'

/** Normalized names of every player on a current 40-man roster — the guard set
 *  for dropping fabricated trade participants from parsed briefs. */
const VALID_PLAYER_NAMES: Set<string> = (() => {
  const s = new Set<string>()
  for (const t of roster.teams) for (const p of t.players) if (p.name) s.add(normalizePlayerName(p.name))
  return s
})()

// ── AI intelligence brief (bring-your-own-Claude) ──────────────────────────────

const KEY_LS = 'warroom-anthropic-key'
const MODEL_LS = 'warroom-anthropic-model'
const DEFAULT_MODEL = 'claude-sonnet-4-5'

export function AiBrief({ promptInput }: { promptInput: PromptInput }) {
  const team = promptInput.team.code
  const storageKey = `warroom-brief-${team}`
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [generating, setGenerating] = useState(false)
  const [working, setWorking] = useState(false)        // manual prompt/paste fallback panel
  const [prompt, setPrompt] = useState('')
  const [pasteRaw, setPasteRaw] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [watching, setWatching] = useState(false)     // polling the file-drop inbox
  const [manualPaste, setManualPaste] = useState(false) // reveal the paste fallback
  // Key/model hydrate synchronously from localStorage on mount
  const [apiKey, setApiKey] = useState(() => {
    try { return localStorage.getItem(KEY_LS) ?? '' } catch { return '' }
  })
  const [model, setModel] = useState(() => {
    try { return localStorage.getItem(MODEL_LS) || DEFAULT_MODEL } catch { return DEFAULT_MODEL }
  })
  const abortRef = useRef<AbortController | null>(null)
  useEffect(() => { try { localStorage.setItem(KEY_LS, apiKey) } catch { /* ignore */ } }, [apiKey])
  useEffect(() => { try { localStorage.setItem(MODEL_LS, model) } catch { /* ignore */ } }, [model])

  // Load the brief when the team changes: localStorage first (instant), then the
  // DuckDB-exported inbox file (canonical source of truth) if one is present.
  useEffect(() => {
    setReport(null); setWorking(false); setPrompt(''); setPasteRaw(''); setError(null)
    setFullscreen(false); setWatching(false); setManualPaste(false)
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) setReport(JSON.parse(saved) as AnalysisReport)
    } catch { /* ignore corrupt cache */ }
    let alive = true
    fetch(`/brief-inbox/${team}.json?t=${Date.now()}`, { cache: 'no-store' })
      .then(r => (r.ok ? r.text() : null))
      .then(text => {
        if (!alive || !text || !text.trim()) return
        try {
          const r = parseAnalysisReport(text, VALID_PLAYER_NAMES); r.team = team
          setReport(r)
          try { localStorage.setItem(storageKey, JSON.stringify(r)) } catch { /* quota */ }
        } catch { /* no valid brief on disk yet */ }
      })
      .catch(() => { /* offline / missing */ })
    return () => { alive = false }
  }, [storageKey, team])

  const persist = useCallback(
    (r: AnalysisReport) => { try { localStorage.setItem(storageKey, JSON.stringify(r)) } catch { /* quota */ } },
    [storageKey],
  )
  const accept = useCallback((raw: string) => {
    const r = parseAnalysisReport(raw, VALID_PLAYER_NAMES); r.team = team
    setReport(r); persist(r); setError(null); setWorking(false); setWatching(false)
  }, [team, persist])

  // File-drop bridge (SHC pattern): poll the inbox a Claude Code run writes to.
  // Vite serves frontend/public at root, so a run that writes
  // frontend/public/brief-inbox/<TEAM>.json lands at /brief-inbox/<TEAM>.json.
  useEffect(() => {
    if (!watching) return
    let alive = true
    const tick = async () => {
      try {
        const res = await fetch(`/brief-inbox/${team}.json?t=${Date.now()}`, { cache: 'no-store' })
        if (!res.ok || !alive) return
        const text = await res.text()
        if (!text.trim()) return
        try { accept(text) } catch { /* not a valid brief yet — keep polling */ }
      } catch { /* network/404 — keep polling */ }
    }
    void tick()
    const id = window.setInterval(tick, 3000)
    return () => { alive = false; window.clearInterval(id) }
  }, [watching, team, accept])

  const generateLive = async () => {
    setError(null)
    const p = buildAnalysisPrompt(promptInput)
    setPrompt(p)
    if (!apiKey.trim()) {
      setSettingsOpen(true); setWorking(true)
      navigator.clipboard?.writeText(p).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {})
      setError('No API key set — add one above to generate in-app, or copy the prompt below and paste Claude\'s reply.')
      return
    }
    setGenerating(true)
    const ctrl = new AbortController(); abortRef.current = ctrl
    try {
      const raw = await generateBriefRaw(p, { apiKey: apiKey.trim(), model: model.trim() || DEFAULT_MODEL, signal: ctrl.signal })
      accept(raw)
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') { /* cancelled */ }
      else {
        setError(`${e instanceof Error ? e.message : 'Generation failed.'} — or copy the prompt below and paste Claude's reply.`)
        setWorking(true)
        navigator.clipboard?.writeText(p).catch(() => {})
      }
    } finally { setGenerating(false); abortRef.current = null }
  }

  const cancel = () => { abortRef.current?.abort(); setGenerating(false) }
  const generatePrompt = () => {
    const p = buildAnalysisPrompt(promptInput)
    setPrompt(p)
    setWorking(true)
    setWatching(true)        // start watching the inbox for a Claude Code drop
    setError(null)
    navigator.clipboard?.writeText(p)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) })
      .catch(() => { /* clipboard blocked; prompt still visible */ })
  }
  const copyPrompt = () => {
    const p = prompt || buildAnalysisPrompt(promptInput)
    navigator.clipboard?.writeText(p).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000) }).catch(() => {})
  }
  const renderPasted = () => {
    try { accept(pasteRaw) } catch (e) { setError(e instanceof Error ? e.message : 'Could not parse the response.') }
  }
  const clear = () => {
    setReport(null); setPasteRaw(''); setError(null); setFullscreen(false); setWatching(false)
    try { localStorage.removeItem(storageKey) } catch { /* ignore */ }
  }

  const header = (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <Brain className="h-4 w-4 text-accent-400" />
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-ink-200">AI Intelligence Brief</span>
        <span className="font-mono text-[8.5px] text-ink-500">full-data strategic analysis</span>
      </div>
      <div className="flex items-center gap-1.5">
        <button onClick={() => setSettingsOpen(s => !s)} title="API settings"
          className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-400 transition-colors hover:border-accent-500/40 hover:text-accent-300">
          <Settings className="h-3 w-3" />
        </button>
        {report && (
          <button onClick={() => setFullscreen(true)}
            className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-400 transition-colors hover:border-accent-500/40 hover:text-accent-300">
            <Maximize2 className="h-3 w-3" />EXPAND
          </button>
        )}
        {!generating ? (
          <>
            <button onClick={generatePrompt}
              className="flex items-center gap-1 rounded border border-accent-500/40 bg-accent-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-accent-300 transition-colors hover:bg-accent-500/20">
              <FileText className="h-3 w-3" />{report ? 'REGENERATE PROMPT' : 'GENERATE PROMPT'}
            </button>
            <button onClick={generateLive} title="Generate in-app via the Anthropic API (needs a key in settings)"
              className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-400 transition-colors hover:border-accent-500/40 hover:text-accent-300">
              <Wand2 className="h-3 w-3" />RUN IN-APP
            </button>
          </>
        ) : (
          <button onClick={cancel}
            className="flex items-center gap-1 rounded border border-negative-500/40 bg-negative-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-negative-400">
            <X className="h-3 w-3" />CANCEL
          </button>
        )}
        {report && (
          <button onClick={clear}
            className="flex items-center gap-1 rounded border border-ink-700 px-2 py-1 font-mono text-[9px] text-ink-500 transition-colors hover:border-negative-500/40 hover:text-negative-400">
            <Trash2 className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  )

  return (
    <div className="rounded-lg border border-accent-500/25 bg-gradient-to-b from-accent-500/[0.05] to-transparent p-4">
      {header}

      {/* Settings: API key + model */}
      {settingsOpen && (
        <div className="mb-3 rounded-lg border border-ink-700 bg-ink-900/60 p-3">
          <div className="mb-2 flex items-center gap-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
            <KeyRound className="h-3 w-3" />Anthropic API
          </div>
          <div className="grid gap-2 sm:grid-cols-[2fr_1fr]">
            <input
              type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
              placeholder="sk-ant-… (stored only in this browser)"
              className="rounded border border-ink-700 bg-ink-950/60 px-2 py-1 font-mono text-[10px] text-ink-200 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
            />
            <input
              type="text" value={model} onChange={e => setModel(e.target.value)}
              placeholder="model id"
              className="rounded border border-ink-700 bg-ink-950/60 px-2 py-1 font-mono text-[10px] text-ink-200 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
            />
          </div>
          <p className="mt-1.5 font-mono text-[8px] leading-relaxed text-ink-600">
            Key is stored in this browser's localStorage and sent directly to Anthropic (dangerous-direct-browser-access).
            Fine for a local personal tool; for a public deploy, proxy through a backend. Update the model id if your account uses a different one.
          </p>
        </div>
      )}

      {/* Generating banner */}
      {generating && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-accent-500/30 bg-accent-500/[0.06] px-3 py-2.5">
          <Loader2 className="h-4 w-4 animate-spin text-accent-400" />
          <span className="font-mono text-[11px] text-accent-300">Consulting Claude — drafting the brief…</span>
        </div>
      )}

      {/* Watching inbox banner (file-drop bridge) */}
      {watching && !report && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-positive-500/25 bg-positive-500/[0.05] px-3 py-2.5">
          <motion.span animate={{ opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 1.4 }}
            className="inline-block h-2 w-2 shrink-0 rounded-full bg-positive-400" />
          <span className="flex-1 font-mono text-[10px] leading-relaxed text-positive-300">
            Watching <span className="text-positive-200">brief-inbox/{team}.json</span> — run the prompt in Claude Code and it lands here automatically.
          </span>
          <button onClick={() => setWatching(false)} className="font-mono text-[9px] text-ink-500 hover:text-ink-300">stop</button>
        </div>
      )}

      {/* Manual fallback: prompt + paste */}
      {working && !generating && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-4 space-y-3">
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="font-mono text-[9px] font-semibold uppercase tracking-[0.2em] text-ink-400">
                ① copy prompt → run in Claude Code
              </span>
              <button onClick={copyPrompt} className="flex items-center gap-1 rounded border border-ink-700 px-1.5 py-0.5 font-mono text-[8.5px] text-ink-400 hover:text-accent-300">
                {copied ? <><Check className="h-2.5 w-2.5 text-positive-400" />COPIED</> : <><ClipboardCopy className="h-2.5 w-2.5" />COPY</>}
              </button>
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded bg-ink-950/60 p-2 font-mono text-[9px] leading-relaxed text-ink-400">{prompt}</pre>
          </div>
          <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
            <div className="font-mono text-[9px] leading-relaxed text-ink-400">
              <span className="font-semibold uppercase tracking-[0.2em] text-positive-300">② it uploads itself</span><br />
              Run the prompt in Claude Code — or just <span className="text-ink-200">/trade-brief {team}</span> — and it persists to
              DuckDB and writes the inbox. This panel renders it automatically. No pasting.
            </div>
            <button onClick={() => setManualPaste(v => !v)} className="mt-2 font-mono text-[9px] text-ink-600 hover:text-ink-300">
              {manualPaste ? '▾ hide manual paste' : '▸ paste the response manually instead'}
            </button>
            {manualPaste && (
              <div className="mt-2">
                <textarea
                  value={pasteRaw} onChange={e => setPasteRaw(e.target.value)}
                  placeholder="Paste the full response — fences and prose handled automatically…" rows={4}
                  className="w-full resize-y rounded border border-ink-700 bg-ink-950/60 p-2 font-mono text-[10px] text-ink-200 placeholder:text-ink-600 focus:border-accent-500/50 focus:outline-none"
                />
                <button onClick={renderPasted} disabled={!pasteRaw.trim()}
                  className="mt-2 flex items-center gap-1 rounded border border-positive-500/40 bg-positive-500/10 px-2.5 py-1 font-mono text-[9px] font-semibold text-positive-400 transition-colors hover:bg-positive-500/20 disabled:cursor-not-allowed disabled:opacity-40">
                  <RefreshCw className="h-3 w-3" />RENDER BRIEF
                </button>
              </div>
            )}
            <div className="mt-2">
              <button onClick={() => { setWorking(false); setError(null) }} className="font-mono text-[9px] text-ink-600 hover:text-ink-300">close</button>
            </div>
          </div>
        </motion.div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-3 flex items-start gap-1.5 rounded border border-negative-500/30 bg-negative-500/5 px-2 py-1.5 font-mono text-[9px] leading-relaxed text-negative-400">
          <X className="mt-0.5 h-3 w-3 shrink-0" />{error}
        </div>
      )}

      {/* Empty CTA */}
      {!report && !generating && !working && (
        <div className="rounded-lg border border-dashed border-accent-500/20 bg-accent-500/[0.03] px-6 py-8">
          <div className="flex flex-col items-center text-center">
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-xl border border-accent-500/25 bg-accent-500/[0.08]">
              <Brain className="h-7 w-7 text-accent-400" />
            </div>
            <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.2em] text-ink-300">
              Strategic Brief — Not Yet Generated
            </div>
            <p className="mb-5 max-w-lg text-[11px] leading-relaxed text-ink-500">
              One click pre-loads standings, holes, payroll, the contention window, buy-low targets, and
              clearing deals into a structured GM prompt. Run it in Claude Code with{' '}
              <span className="font-mono text-accent-300">/trade-brief {promptInput.team.code}</span>{' '}
              and it renders here automatically — no paste required.
            </p>
            <div className="flex items-center gap-3">
              <div className="flex flex-col items-start gap-1 rounded-lg border border-ink-700 bg-ink-900/80 px-4 py-3 text-left">
                <span className="font-mono text-[8px] uppercase tracking-[0.2em] text-ink-500">Claude Code</span>
                <span className="font-mono text-[12px] font-bold text-accent-300">/trade-brief {promptInput.team.code}</span>
              </div>
              <span className="font-mono text-[10px] text-ink-600">or</span>
              <div className="flex flex-col items-start gap-1 rounded-lg border border-ink-700 bg-ink-900/80 px-4 py-3 text-left">
                <span className="font-mono text-[8px] uppercase tracking-[0.2em] text-ink-500">In-app (API key required)</span>
                <span className="font-mono text-[12px] font-bold text-ink-300">Settings → Run In-App</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Staleness banner: brief predates the current war-room snapshot */}
      {report?.generatedAt && new Date(report.generatedAt) < new Date(warRoomIndex.generatedAt) && (
        <div className="flex items-center gap-2 rounded-md border border-amber-700/50 bg-amber-500/5 px-3 py-1.5 font-mono text-[9px] text-amber-400">
          <span>⚠</span>
          <span>
            Brief generated {new Date(report.generatedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} —
            against an older snapshot than the current war room ({new Date(warRoomIndex.generatedAt).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}).
            Regenerate for fresh context.
          </span>
        </div>
      )}

      {/* Rendered brief (inline) */}
      {report && !fullscreen && <IntelligenceReport report={report} />}

      {/* Fullscreen brief screen */}
      {report && fullscreen && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-ink-950/98 backdrop-blur-sm">
          <div className="mx-auto max-w-[1200px] px-6 py-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Brain className="h-5 w-5 text-accent-400" />
                <span className="display text-[18px] font-black text-ink-100">{team} · Intelligence Brief</span>
              </div>
              <button onClick={() => setFullscreen(false)}
                className="flex items-center gap-1 rounded border border-ink-700 px-2.5 py-1 font-mono text-[10px] text-ink-300 transition-colors hover:border-accent-500/40 hover:text-accent-300">
                <X className="h-3.5 w-3.5" />CLOSE
              </button>
            </div>
            <IntelligenceReport report={report} />
          </div>
        </div>
      )}
    </div>
  )
}
