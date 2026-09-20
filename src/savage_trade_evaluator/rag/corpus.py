"""Load and chunk the project's markdown corpus for retrieval.

The corpus has two layers:
  1. Project docs: the project's own documented thinking, such as the research log,
     synthesis docs, stats catalog.
  2. Vault wiki: ingested book and paper notes plus concept pages, loaded
     alongside project docs so retrieval spans both. Location defaults to
     ~/Vault/savage_vault/wiki/ and can be overridden with STE_VAULT_DIR;
     a missing vault degrades to project docs only.

Chunks are split on markdown headings and then windowed so each chunk is a
self-contained, citable passage.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from savage_trade_evaluator.config import PROJECT_ROOT

# Files that make up the project-docs layer, relative to the project root.
CORPUS_FILES: tuple[str, ...] = (
    "docs/research/part-1-baseline-and-first-ablations.md",
    "docs/research/part-2-origin-org-and-the-metric-correction.md",
    "docs/research/part-3-omnibus-ablations-and-regime-control.md",
    "docs/research/part-4-decomposition-dev-credit-and-fortification.md",
    "docs/PHASE1_SYNTHESIS.md",
    "docs/NAIVE_BASELINE.md",
    "docs/STATS_CATALOG.md",
    "docs/EXPERIMENT_PROTOCOL.md",
    "docs/archive/V2_DESIGN.md",
    "docs/archive/DATA_SOURCE_PROBE.md",
)

# Vault wiki directory, outside the project root, overridable for other machines.
VAULT_DIR = Path(os.environ.get("STE_VAULT_DIR", Path.home() / "Vault" / "savage_vault" / "wiki"))

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
_FRONTMATTER = re.compile(r"^---\n.*?^---\n", re.DOTALL | re.MULTILINE)
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


def _strip_frontmatter(text: str) -> str:
    r"""Remove YAML frontmatter block (---\n...\n---) from vault note text."""
    return _FRONTMATTER.sub("", text, count=1).lstrip()


def load_chunks(root: Path | None = None, *, include_vault: bool | None = None) -> list[Chunk]:
    """Load and chunk every corpus file that exists, plus the vault wiki.

    Args:
        root: Project root to resolve corpus paths against. Defaults to
            ``config.PROJECT_ROOT``.
        include_vault: Whether to append vault wiki chunks. Defaults to True
            only when ``root`` is the real project root. An explicit root
            (tests, alternate corpora) stays hermetic unless requested.

    Returns:
        All chunks across the corpus (project docs + vault), in document order.

    Raises:
        FileNotFoundError: If none of the project corpus files are present.
    """
    if include_vault is None:
        include_vault = root is None
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
    if include_vault:
        chunks.extend(load_vault_chunks())
    return chunks


def load_vault_chunks(vault_dir: Path | None = None) -> list[Chunk]:
    """Load and chunk all markdown pages from the savage_vault wiki.

    Strips YAML frontmatter before chunking so retrieved passages contain
    only the prose body. Source labels use ``vault:<filename>`` so citations
    are distinguishable from project-doc sources.

    Args:
        vault_dir: Path to the wiki directory. Defaults to ``VAULT_DIR``.

    Returns:
        All vault chunks in filename order. Empty list if the vault does not
        exist (allows offline / CI use without the vault present).
    """
    base = vault_dir or VAULT_DIR
    if not base.exists():
        return []
    chunks: list[Chunk] = []
    for path in sorted(base.glob("*.md")):
        markdown = _strip_frontmatter(path.read_text(encoding="utf-8"))
        source = f"vault:{path.name}"
        for heading, body in _sections(markdown):
            for passage in _window(body):
                chunks.append(Chunk(source=source, heading=heading, text=passage))
    return chunks
