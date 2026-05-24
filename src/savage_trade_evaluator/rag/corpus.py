"""Load and chunk the project's markdown corpus for retrieval.

The corpus is the project's own documented thinking: the research log, the
synthesis docs, and the stats catalog. Chunks are split on markdown headings
and then windowed so each chunk is a self-contained, citable passage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from savage_trade_evaluator.config import PROJECT_ROOT

# Files that make up the retrievable corpus, relative to the project root.
CORPUS_FILES: tuple[str, ...] = (
    "RESEARCH_LOG.md",
    "docs/PHASE1_SYNTHESIS.md",
    "docs/NAIVE_BASELINE.md",
    "docs/STATS_CATALOG.md",
    "docs/EXPERIMENT_PROTOCOL.md",
    "docs/V2_DESIGN.md",
    "docs/DATA_SOURCE_PROBE.md",
)

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_WORDS_PER_CHUNK = 160
_OVERLAP_WORDS = 32


@dataclass(frozen=True)
class Chunk:
    """A retrievable passage with enough provenance to cite it.

    Attributes:
        source: Corpus file path, relative to the project root.
        heading: The nearest enclosing markdown heading trail.
        text: The passage text.
    """

    source: str
    heading: str
    text: str


def _sections(markdown: str) -> list[tuple[str, str]]:
    """Split markdown into (heading_trail, body) sections by heading.

    Args:
        markdown: Raw markdown text.

    Returns:
        A list of (heading trail, body text) tuples in document order.
    """
    trail: list[str] = []
    sections: list[tuple[str, str]] = []
    buf: list[str] = []
    heading = "(preamble)"

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((heading, body))

    for line in markdown.splitlines():
        m = _HEADING.match(line)
        if m:
            flush()
            buf = []
            depth = len(m.group(1))
            trail = trail[: depth - 1]
            trail.append(m.group(2).strip())
            heading = " > ".join(trail)
        else:
            buf.append(line)
    flush()
    return sections


def _window(text: str) -> list[str]:
    """Window a section body into overlapping word-bounded passages.

    Args:
        text: Section body text.

    Returns:
        A list of passage strings. Short sections yield a single passage.
    """
    words = text.split()
    if len(words) <= _WORDS_PER_CHUNK:
        return [text]
    step = _WORDS_PER_CHUNK - _OVERLAP_WORDS
    return [
        " ".join(words[i : i + _WORDS_PER_CHUNK])
        for i in range(0, len(words), step)
        if words[i : i + _WORDS_PER_CHUNK]
    ]


def load_chunks(root: Path | None = None) -> list[Chunk]:
    """Load and chunk every corpus file that exists.

    Args:
        root: Project root to resolve corpus paths against. Defaults to
            ``config.PROJECT_ROOT``.

    Returns:
        All chunks across the corpus, in document order.

    Raises:
        FileNotFoundError: If none of the corpus files are present.
    """
    base = root or PROJECT_ROOT
    chunks: list[Chunk] = []
    found = False
    for rel in CORPUS_FILES:
        path = base / rel
        if not path.exists():
            continue
        found = True
        markdown = path.read_text(encoding="utf-8")
        for heading, body in _sections(markdown):
            for passage in _window(body):
                chunks.append(Chunk(source=rel, heading=heading, text=passage))
    if not found:
        raise FileNotFoundError(
            f"No corpus files found under {base}. Expected one of: {', '.join(CORPUS_FILES)}"
        )
    return chunks
