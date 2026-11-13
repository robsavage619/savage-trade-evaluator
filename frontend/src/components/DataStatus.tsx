import { useEffect, useState } from 'react'

type Status = {
  status: 'ok' | 'degraded' | 'failed'
  finished: string
  data_as_of: string | null
  published: boolean
  problems: string[]
}

const TONE = { ok: 'text-emerald-400', degraded: 'text-amber-400', failed: 'text-red-400' }

function ago(iso: string, now: number): string {
  const hours = (now - new Date(iso).getTime()) / 3.6e6
  return hours < 1 ? 'under an hour ago' : hours < 48 ? `${Math.round(hours)}h ago` : `${Math.round(hours / 24)}d ago`
}

export default function DataStatus() {
  const [s, setS] = useState<Status | null>(null)
  const [now] = useState(() => Date.now())
  useEffect(() => {
    fetch('/status.json', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then(setS)
      .catch(() => setS(null))
  }, [])
  if (!s) return null
  const stale = s.data_as_of ? now - new Date(s.data_as_of).getTime() > 36 * 3.6e6 : true
  const tone = s.status !== 'ok' ? TONE[s.status] : stale ? TONE.degraded : TONE.ok
  const label = s.data_as_of ? `Data ${ago(s.data_as_of, now)}` : 'Data age unknown'
  const note = !s.published
    ? `last refresh failed, serving data from before it${s.problems.length ? `: ${s.problems.slice(0, 3).join('; ')}` : ''}`
    : s.problems.length
      ? `${s.problems.length} source(s) lagging: ${s.problems.slice(0, 3).join('; ')}`
      : ''
  return (
    <span className="mono" title={s.problems.join('\n')}>
      <span className={tone}>●</span> {label}
      {note && ` · ${note}`}
    </span>
  )
}
