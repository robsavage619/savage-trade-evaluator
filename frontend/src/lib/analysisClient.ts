/**
 * Direct browser → Anthropic Messages API call for in-app brief generation.
 *
 * ARCHITECTURE NOTE: this is a static frontend with no backend. The API key is
 * read from localStorage and sent directly from the browser using the
 * `anthropic-dangerous-direct-browser-access` header (which enables CORS).
 * Acceptable for a local personal tool; for a public deploy, proxy through a
 * server so the key never reaches the client.
 */

const ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'

export type GenOptions = {
  apiKey: string
  model: string
  maxTokens?: number
  signal?: AbortSignal
}

type ContentBlock = { type: string; text?: string }
type MessagesResponse = { content?: ContentBlock[]; error?: { message?: string; type?: string } }

/** Calls Claude and returns the raw text of the response (JSON still embedded). */
export async function generateBriefRaw(prompt: string, opts: GenOptions): Promise<string> {
  let res: Response
  try {
    res = await fetch(ANTHROPIC_URL, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': opts.apiKey,
        'anthropic-version': '2023-06-01',
        'anthropic-dangerous-direct-browser-access': 'true',
      },
      body: JSON.stringify({
        model: opts.model,
        max_tokens: opts.maxTokens ?? 8192,
        messages: [{ role: 'user', content: prompt }],
      }),
      signal: opts.signal,
    })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new Error('Network/CORS error reaching Anthropic — check your connection or use the manual prompt fallback.')
  }

  if (!res.ok) {
    let detail = ''
    try {
      const j = (await res.json()) as MessagesResponse
      detail = j?.error?.message ?? ''
    } catch { /* non-JSON error body */ }
    if (res.status === 401) throw new Error('Invalid API key (401). Check the key in settings.')
    if (res.status === 404) throw new Error(`Model not found (404)${detail ? `: ${detail}` : ''}. Update the model ID in settings.`)
    if (res.status === 429) throw new Error('Rate limited (429). Wait a moment and retry.')
    throw new Error(`Anthropic API ${res.status}${detail ? `: ${detail}` : ''}`)
  }

  const data = (await res.json()) as MessagesResponse
  const text = (data.content ?? [])
    .filter(b => b.type === 'text' && typeof b.text === 'string')
    .map(b => b.text as string)
    .join('\n')
    .trim()
  if (!text) throw new Error('Claude returned an empty response.')
  return text
}
