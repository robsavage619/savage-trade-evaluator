import { useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowLeftRight, Brain, Terminal, Trash2, BadgePlus, Coins, Gauge } from 'lucide-react'
import { type CurrentPlayer, type CurrentTeam } from '../data/players'
import { useRoster, useTeamsByBref } from '../lib/rosterStore'
import { useIdentityStore, TEAM_THEME } from '../lib/identityStore'
import { TeamIdentitySwitcher } from '../components/TeamIdentitySwitcher'
import { PlayerPicker, BasketCard } from '../components/PlayerPicker'
import { RefreshRostersButton } from '../components/RefreshRostersButton'
import { PosteriorViolin } from '../components/PosteriorViolin'
import { Section, Stat } from '../components/Section'
import { TeamLogo } from '../components/TeamLogo'
import { computeVerdict } from '../lib/hypothetical'
import { composeHypotheticalPrompt } from '../lib/composeHypothetical'
import { fmtSigned, fmtMoney } from '../lib/format'
import { useReasoningStore, parseReasoningResponse } from '../lib/reasoningStore'
import { AnimatePresence } from 'framer-motion'
import { X, Copy, ClipboardCheck, AlertCircle, CheckCircle2, RotateCcw, Sparkles } from 'lucide-react'

/** Pseudo-id namespace for hypothetical trades — kept negative to avoid colliding
 *  with real trade_event_ids. */
const HYPO_BASE = -1_000_000

export default function TradeBuilder() {
  const yourBref = useIdentityStore((s) => s.activeTeam)
  const roster = useRoster()
  const teamsByBref = useTeamsByBref()
  const yourTeam = teamsByBref[yourBref] ?? teamsByBref.NYM
  const theme = TEAM_THEME[yourBref] ?? TEAM_THEME.NYM
  const [partnerBref, setPartnerBref] = useState<string>('TBR')
  const partnerTeam = teamsByBref[partnerBref] ?? teamsByBref.TBR

  const [sentIds, setSentIds] = useState<number[]>([])
  const [receivedIds, setReceivedIds] = useState<number[]>([])

  const sendingPlayers = useMemo<CurrentPlayer[]>(
    () => sentIds.map((id) => yourTeam.players.find((p) => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [sentIds, yourTeam],
  )
  const receivingPlayers = useMemo<CurrentPlayer[]>(
    () => receivedIds.map((id) => partnerTeam.players.find((p) => p.mlb_player_id === id)).filter(Boolean) as CurrentPlayer[],
    [receivedIds, partnerTeam],
  )

  const verdict = useMemo(
    () => computeVerdict({ sending: { team: yourTeam, players: sendingPlayers }, receiving: { team: partnerTeam, players: receivingPlayers } }),
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers],
  )

  function addToSent(p: CurrentPlayer, t: CurrentTeam) {
    if (t.bref !== yourBref) return // ignore if user picks from non-self
    if (sentIds.includes(p.mlb_player_id)) return
    setSentIds([...sentIds, p.mlb_player_id])
  }
  function addToReceived(p: CurrentPlayer, t: CurrentTeam) {
    if (t.bref !== partnerBref) setPartnerBref(t.bref)
    if (receivedIds.includes(p.mlb_player_id)) return
    setReceivedIds((prev) => [...prev, p.mlb_player_id])
  }
  function removeSent(id: number) { setSentIds((s) => s.filter((x) => x !== id)) }
  function removeReceived(id: number) { setReceivedIds((s) => s.filter((x) => x !== id)) }

  function swapSides() {
    // swap rosters — your team becomes partner, partner becomes you
    const oldPartner = partnerBref
    const oldSent = sentIds
    const oldReceived = receivedIds
    setPartnerBref(yourBref)
    // change identity store
    useIdentityStore.getState().setActiveTeam(oldPartner)
    setSentIds(oldReceived)
    setReceivedIds(oldSent)
  }

  const selectedAllIds = useMemo(() => new Set<number>([...sentIds, ...receivedIds]), [sentIds, receivedIds])

  // Claude Code drawer state
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [pasteError, setPasteError] = useState<string | null>(null)
  const [pasteOk, setPasteOk] = useState(false)
  const [copied, setCopied] = useState(false)
  const hypoId = useMemo(() => {
    // Stable-ish id from the selection signature so saved analyses survive across the same hypothetical
    const sig = `${yourBref}|${partnerBref}|${[...sentIds].sort().join(',')}|${[...receivedIds].sort().join(',')}`
    let h = 0
    for (let i = 0; i < sig.length; i++) h = (h * 31 + sig.charCodeAt(i)) | 0
    return HYPO_BASE - Math.abs(h)
  }, [yourBref, partnerBref, sentIds, receivedIds])

  const override = useReasoningStore((s) => s.overrides[hypoId])
  const setReasoning = useReasoningStore((s) => s.set)

  const prompt = useMemo(
    () => verdict ? composeHypotheticalPrompt({ yourTeam, partnerTeam, sending: sendingPlayers, receiving: receivingPlayers, verdict }) : '',
    [yourTeam, partnerTeam, sendingPlayers, receivingPlayers, verdict],
  )

  async function copyPrompt() {
    if (!prompt) return
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  function applyPaste() {
    setPasteError(null)
    setPasteOk(false)
    const r = parseReasoningResponse(pasteText)
    if ('error' in r) {
      setPasteError(r.error)
      return
    }
    setReasoning(hypoId, r, 'Claude Code · hypothetical')
    setPasteOk(true)
  }

  return (
    <main className="mx-auto max-w-[1640px] px-6 py-6">
      {/* Top control band */}
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="card mb-5 overflow-hidden"
      >
        <div
          className="h-1 w-full"
          style={{ background: `linear-gradient(90deg, ${theme.primary}, ${theme.secondary})` }}
          aria-hidden
        />
        <div className="flex flex-wrap items-center justify-between gap-4 p-4">
          <div className="flex items-center gap-3">
            <TeamLogo team={yourBref} size={40} />
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Trade Builder · You are</div>
              <div className="text-[16px] font-semibold tracking-tight text-ink-100">{yourTeam.name}</div>
              <div className="text-[11px] text-ink-400">Workshop a hypothetical against any club. All verdicts framed from {yourBref}'s side.</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <RefreshRostersButton />
            <span className="hidden h-6 w-px bg-ink-700 md:block" />
            <TeamIdentitySwitcher />
            <span className="hidden h-6 w-px bg-ink-700 md:block" />
            <button
              onClick={swapSides}
              className="inline-flex items-center gap-1.5 rounded-md border border-ink-700 px-2.5 py-1.5 text-[11px] font-medium text-ink-200 transition-colors hover:border-accent-500/60 hover:text-ink-100"
              title="Flip identities — see the deal from the other GM's seat"
            >
              <ArrowLeftRight className="h-3 w-3" /> Flip sides
            </button>
            <button
              onClick={() => { setSentIds([]); setReceivedIds([]) }}
              className="inline-flex items-center gap-1.5 rounded-md border border-ink-700 px-2.5 py-1.5 text-[11px] font-medium text-ink-300 transition-colors hover:border-negative-500/60 hover:text-negative-500"
            >
              <Trash2 className="h-3 w-3" /> Clear baskets
            </button>
          </div>
        </div>
      </motion.div>

      {/* Verdict band */}
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="card mb-6 p-5">
        {verdict ? (
          <div className="flex flex-wrap items-end justify-between gap-6">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Live verdict — {yourBref} perspective</div>
              <div className="mt-1 text-[20px] font-semibold tracking-tight text-ink-100">{verdict.recommendationLabel}</div>
              <div className="mt-1 text-[12px] text-ink-400">
                Sent {sendingPlayers.length} · Received {receivingPlayers.length} · {yourBref} dev-multiplier {verdict.acquirerDevMultiplier.toFixed(2)}× applied to acquired players
              </div>
            </div>
            <div className="flex items-end gap-7">
              <Stat label="3-yr surplus" value={fmtSigned(verdict.surplusMean)} sub={`90% [${verdict.surplusLo.toFixed(2)}, ${verdict.surplusHi.toFixed(2)}]`} tone={verdict.reasoningTone} />
              <Stat label="P(positive)" value={`${Math.round(verdict.pPositive * 100)}%`} sub="Posterior > 0" tone={verdict.reasoningTone} />
              <Stat label="WAR Δ" value={fmtSigned(verdict.warReceived - verdict.warSent, 1)} sub={`R ${verdict.warReceived.toFixed(1)} · S ${verdict.warSent.toFixed(1)}`} tone="neutral" />
              <Stat label="Salary Δ" value={`${verdict.costReceived - verdict.costSent >= 0 ? '+' : ''}${fmtMoney(Math.abs(verdict.costReceived - verdict.costSent))}`.replace('$', verdict.costReceived - verdict.costSent >= 0 ? '$' : '−$')} sub={`R ${fmtMoney(verdict.costReceived)} · S ${fmtMoney(verdict.costSent)}`} tone="neutral" />
            </div>
            <div className="w-full pt-1 md:w-[420px]">
              <PosteriorViolin
                mean={verdict.surplusMean}
                sd={verdict.surplusSd}
                min={Math.min(verdict.surplusLo, -3)}
                max={Math.max(verdict.surplusHi, 3)}
                accent={verdict.reasoningTone}
                unit=" WAR"
                width={420}
                height={70}
              />
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 text-[13px] text-ink-300">
            <BadgePlus className="h-4 w-4 text-accent-400" />
            Add a player to either basket below to begin. The verdict updates live as you build.
          </div>
        )}
      </motion.div>

      {/* AI Reasoning bar */}
      <div className="card mb-6 flex flex-wrap items-center justify-between gap-3 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400">
            <Brain className="h-4 w-4" strokeWidth={2.2} />
          </div>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">AI Reasoning</div>
            <div className="text-[13px] text-ink-200">
              {override
                ? <span>Loaded analysis from Claude Code · saved {new Date(override.savedAt).toLocaleString()}.</span>
                : 'Get a structured analysis: copy the prompt, paste into Claude Code chat, paste JSON back.'}
            </div>
          </div>
        </div>
        <button
          onClick={() => setDrawerOpen(true)}
          disabled={!verdict}
          className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 transition-colors hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-500"
        >
          <Terminal className="h-3.5 w-3.5" /> Reason with Claude Code
        </button>
      </div>

      {override?.reasoning ? (
        <div className="card mb-6 p-5">
          <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Claude&apos;s headline</div>
          <div className="text-[15px] font-semibold leading-snug text-ink-100">{override.reasoning.headline}</div>
          <div className="mt-4 grid gap-4 md:grid-cols-[1fr_280px]">
            <div className="space-y-3 text-[13px] leading-relaxed text-ink-200">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Thesis</div>
                <p className="mt-1">{override.reasoning.thesis}</p>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Key drivers</div>
                <ul className="mt-1 space-y-2">
                  {override.reasoning.keyDrivers.map((d, i) => (
                    <li key={i} className="rounded-md border border-ink-700 bg-ink-800/40 p-2.5">
                      <div className="flex items-center gap-2">
                        {d.chip ? <span className="chip chip-accent mono">{d.chip}</span> : null}
                        <span className="text-[12.5px] font-semibold text-ink-100">{d.title}</span>
                      </div>
                      <div className="mt-1 text-[12px] text-ink-300">{d.body}</div>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400">Recommendation</div>
                <p className="mt-1 font-semibold text-ink-100">{override.reasoning.recommendation}</p>
              </div>
            </div>
            <div className="space-y-3 border-l border-ink-700 pl-4">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Watch-outs</div>
                <ul className="mt-1 space-y-2 text-[11px]">
                  {override.reasoning.watchOuts.map((w, i) => (
                    <li key={i} className="rounded-md bg-negative-500/[0.06] p-2">
                      <div className="font-semibold text-ink-100">{w.title}</div>
                      <div className="mt-0.5 text-ink-300">{w.body}</div>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Grounding</div>
                <ul className="mt-1 space-y-2 text-[11px]">
                  {override.reasoning.citations.map((c, i) => (
                    <li key={i} className="rounded-md border border-ink-700 bg-ink-800/60 p-2">
                      <div className="mono font-semibold text-accent-300">[{i + 1}] {c.label}</div>
                      <div className="mt-0.5 text-ink-300">{c.detail}</div>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Three-column workshop */}
      <div className="grid gap-5 xl:grid-cols-[1fr_1fr]">
        <Section eyebrow={`${yourBref} sends`} title="Your roster" hint={`Click any player to add to '${yourBref} sends'`}>
          <div className="grid grid-rows-[1fr_180px] gap-3" style={{ height: 'calc(100vh - 320px)', minHeight: 540 }}>
            <PlayerPicker
              team={yourBref}
              onPickTeam={(b) => useIdentityStore.getState().setActiveTeam(b)}
              onAdd={addToSent}
              selectedIds={selectedAllIds}
              title={`${yourBref} 40-man`}
              hint="Filter by position / status; sorted by last-season WAR."
            />
            <BasketCard title={`${yourBref} sends`} team={yourTeam} players={sendingPlayers} onRemove={removeSent} emptyHint="Pick players from your roster above to offer." />
          </div>
        </Section>

        <Section eyebrow={`${yourBref} receives`} title={`Partner: ${partnerTeam.name}`} hint="Pick or search any of the other 29 clubs">
          <div className="grid grid-rows-[1fr_180px] gap-3" style={{ height: 'calc(100vh - 320px)', minHeight: 540 }}>
            <PlayerPicker
              team={partnerBref}
              onPickTeam={(b) => setPartnerBref(b)}
              onAdd={addToReceived}
              selectedIds={selectedAllIds}
              title="Trade-partner roster"
              hint="Pick from any of the other 29 clubs."
            />
            <BasketCard title={`${yourBref} receives`} team={partnerTeam} players={receivingPlayers} onRemove={removeReceived} emptyHint="Pick targets from the partner roster above." />
          </div>
        </Section>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-400">
        <span className="mono">
          Live data · 40-man rosters · {roster.player_count} active players · last sync {new Date(roster.refreshed_at).toLocaleString()} · refresh in header
        </span>
        <span className="mono">
          Synthetic posterior · v1 dev-signature multipliers · context features pre-V2 model
        </span>
      </div>

      {/* Reasoning drawer (inline lightweight version) */}
      <AnimatePresence>
        {drawerOpen && verdict && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-ink-950/70 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }} onClick={() => setDrawerOpen(false)} />
            <motion.aside
              initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }} transition={{ type: 'spring', stiffness: 300, damping: 32 }}
              className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[640px] flex-col border-l border-ink-700 bg-ink-900"
            >
              <header className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="grid h-8 w-8 place-items-center rounded-md bg-accent-500/15 text-accent-400"><Terminal className="h-4 w-4" /></div>
                  <div>
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-accent-400">Reason with Claude Code</div>
                    <div className="text-[14px] font-semibold text-ink-100">{yourBref} ↔ {partnerBref} · {sendingPlayers.length}-for-{receivingPlayers.length} hypothetical</div>
                  </div>
                </div>
                <button onClick={() => setDrawerOpen(false)} className="rounded-md p-1.5 text-ink-400 hover:bg-ink-800 hover:text-ink-100"><X className="h-4 w-4" /></button>
              </header>
              <div className="flex-1 overflow-y-auto p-5">
                <section className="mb-5">
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 1 · Generated prompt</div>
                      <div className="text-[12px] text-ink-300">Bundles trade structure, model snapshot, and ADRs.</div>
                    </div>
                    <button onClick={copyPrompt} className="inline-flex items-center gap-1.5 rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 hover:bg-accent-400">
                      {copied ? <ClipboardCheck className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? 'Copied' : 'Copy prompt'}
                    </button>
                  </div>
                  <pre className="max-h-64 overflow-y-auto rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[11px] leading-relaxed text-ink-300 mono whitespace-pre-wrap">{prompt}</pre>
                </section>
                <section className="mb-5 rounded-md border border-ink-700 bg-ink-800/50 p-4">
                  <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-accent-400"><Sparkles className="h-3 w-3" /> Step 2 · In Claude Code</div>
                  <ol className="ml-4 list-decimal space-y-1 text-[12px] text-ink-200 marker:text-ink-500">
                    <li>Paste the prompt into Claude Code chat</li>
                    <li>Claude returns a single fenced <code className="mono rounded bg-ink-700 px-1 text-[10.5px]">```json</code> block</li>
                    <li>Copy that block (fences OK) and paste below</li>
                  </ol>
                </section>
                <section>
                  <div className="mb-2 flex items-center justify-between">
                    <div>
                      <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-400">Step 3 · Paste response</div>
                      <div className="text-[12px] text-ink-300">JSON validates against AiReasoning schema.</div>
                    </div>
                    {override && (
                      <button onClick={() => { useReasoningStore.getState().clear(hypoId); setPasteText(''); setPasteError(null); setPasteOk(false) }} className="inline-flex items-center gap-1.5 rounded-md border border-ink-600 px-2.5 py-1 text-[11px] text-ink-300 hover:border-negative-500/50 hover:text-negative-500">
                        <RotateCcw className="h-3 w-3" /> Clear saved
                      </button>
                    )}
                  </div>
                  <textarea
                    value={pasteText}
                    onChange={(e) => setPasteText(e.target.value)}
                    placeholder="```json&#10;{ ... }&#10;```"
                    rows={10}
                    className="mono w-full rounded-md border border-ink-700 bg-ink-950/80 p-3 text-[12px] leading-relaxed text-ink-200 placeholder:text-ink-500 focus:border-accent-500/50 focus:outline-none"
                    spellCheck={false}
                  />
                  {pasteError && (
                    <div className="mt-2 flex items-start gap-2 rounded-md border border-negative-500/40 bg-negative-500/10 px-3 py-2 text-[12px] text-negative-500">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{pasteError}</span>
                    </div>
                  )}
                  {pasteOk && (
                    <div className="mt-2 flex items-center gap-2 rounded-md border border-positive-500/40 bg-positive-500/10 px-3 py-2 text-[12px] text-positive-500">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Applied. Reasoning panel updated.
                    </div>
                  )}
                  <div className="mt-3 flex items-center justify-end gap-2">
                    <button onClick={() => setDrawerOpen(false)} className="rounded-md border border-ink-700 px-3 py-1.5 text-[12px] text-ink-300 hover:border-ink-500 hover:text-ink-100">Done</button>
                    <button onClick={applyPaste} disabled={!pasteText.trim()} className="rounded-md bg-accent-500 px-3 py-1.5 text-[12px] font-semibold text-ink-950 hover:bg-accent-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-500">Parse &amp; apply</button>
                  </div>
                </section>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </main>
  )
}
