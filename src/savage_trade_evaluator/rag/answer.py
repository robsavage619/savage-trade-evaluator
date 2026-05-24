"""Grounded answer synthesis over retrieved chunks.

Retrieval always runs first; this module only ever sees chunks that were
retrieved from the index. If an Anthropic API key is present it synthesises a
cited answer with Claude; otherwise it returns the ranked passages verbatim.
Either way the output carries provenance — the generator is never the source
of a fact, only a synthesiser of retrieved ones.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx

from savage_trade_evaluator.rag.store import Hit

logger = logging.getLogger(__name__)

_API_URL = "https://api.anthropic.com/v1/messages"
_DEFAULT_MODEL = "claude-sonnet-4-6"
_SYSTEM = (
    "You answer questions about an MLB trade-evaluation research project using ONLY the "
    "numbered context passages provided. Cite every claim with its passage number like [1]. "
    "If the passages do not contain the answer, say so plainly. Never invent figures, "
    "findings, or citations that are not in the passages."
)


@dataclass(frozen=True)
class Answer:
    """A grounded answer and the hits it was built from.

    Attributes:
        text: The synthesised answer, or the formatted passages if no LLM ran.
        hits: The retrieved chunks used as context, in rank order.
        generated: True if an LLM synthesised the answer; False if passages
            were returned directly (retrieval-only mode).
    """

    text: str
    hits: list[Hit]
    generated: bool


def _context_block(hits: list[Hit]) -> str:
    """Render hits as a numbered, citable context block.

    Args:
        hits: Retrieved chunks in rank order.

    Returns:
        A newline-separated block where each passage is prefixed with [n].
    """
    return "\n\n".join(
        f"[{i}] ({h.source} > {h.heading})\n{h.text}" for i, h in enumerate(hits, start=1)
    )


def _passages_only(hits: list[Hit]) -> str:
    """Format hits for display when no LLM is available.

    Args:
        hits: Retrieved chunks in rank order.

    Returns:
        A human-readable ranked list with similarity scores and provenance.
    """
    lines = ["(retrieval-only — set ANTHROPIC_API_KEY for a synthesised answer)\n"]
    for i, h in enumerate(hits, start=1):
        lines.append(f"[{i}] {h.score:.3f}  {h.source} > {h.heading}\n    {h.text}\n")
    return "\n".join(lines)


def synthesise(query: str, hits: list[Hit], model: str | None = None) -> Answer:
    """Produce a grounded answer from retrieved hits.

    Args:
        query: The user's question.
        hits: Retrieved chunks (already ranked). If empty, no generation runs.
        model: Anthropic model id. Defaults to ``ANTHROPIC_MODEL`` env or a
            built-in default.

    Returns:
        An :class:`Answer`. Falls back to retrieval-only output when no API key
        is set, when there are no hits, or when the API call fails.
    """
    if not hits:
        return Answer(text="No relevant passages found in the corpus.", hits=hits, generated=False)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return Answer(text=_passages_only(hits), hits=hits, generated=False)
    prompt = (
        f"Context passages:\n\n{_context_block(hits)}\n\n"
        f"Question: {query}\n\nAnswer using only the passages above, citing each claim."
    )
    try:
        resp = httpx.post(
            _API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model or os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL),
                "max_tokens": 1024,
                "system": _SYSTEM,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        text = "".join(
            block.get("text", "")
            for block in resp.json().get("content", [])
            if block.get("type") == "text"
        ).strip()
        return Answer(text=text, hits=hits, generated=True)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("LLM synthesis failed (%s); returning retrieval-only output", exc)
        return Answer(text=_passages_only(hits), hits=hits, generated=False)
