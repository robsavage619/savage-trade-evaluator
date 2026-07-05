"""Tests for RAG corpus chunking (no network, no embeddings)."""

from __future__ import annotations

from pathlib import Path

import pytest

from savage_trade_evaluator.rag import corpus


def test_sections_split_on_headings_with_trail() -> None:
    md = "# Top\nintro\n## A\nalpha body\n### A1\nnested body\n## B\nbeta body"
    sections = corpus._sections(md)
    headings = [h for h, _ in sections]
    assert headings == ["Top", "Top > A", "Top > A > A1", "Top > B"]
    assert sections[1][1] == "alpha body"


def test_window_keeps_short_sections_whole() -> None:
    assert corpus._window("three little words") == ["three little words"]


def test_window_overlaps_long_sections() -> None:
    body = " ".join(f"w{i}" for i in range(400))
    passages = corpus._window(body)
    assert len(passages) > 1
    # Consecutive windows share overlap, so the union still covers the start.
    assert passages[0].split()[0] == "w0"
    assert any(p.split()[-1] == "w399" for p in passages)


def test_load_chunks_reads_corpus_files(tmp_path: Path) -> None:
    (tmp_path / "RESEARCH_LOG.md").write_text("# Log\n## R-01\nfirst finding body")
    chunks = corpus.load_chunks(root=tmp_path)
    assert chunks
    assert all(c.source == "RESEARCH_LOG.md" for c in chunks)
    assert "first finding" in chunks[-1].text


def test_load_chunks_raises_when_corpus_absent(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        corpus.load_chunks(root=tmp_path)


def test_strip_frontmatter_removes_yaml_block() -> None:
    text = "---\ntitle: Note\ntags: [a, b]\n---\n# Body\ncontent"
    assert corpus._strip_frontmatter(text) == "# Body\ncontent"


def test_strip_frontmatter_noop_without_block() -> None:
    text = "# Body\ncontent"
    assert corpus._strip_frontmatter(text) == text


def test_load_vault_chunks_labels_sources(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("---\ntitle: N\n---\n# Idea\nvault body text")
    chunks = corpus.load_vault_chunks(vault_dir=tmp_path)
    assert chunks
    assert all(c.source == "vault:note.md" for c in chunks)
    assert not any("title: N" in c.text for c in chunks)


def test_load_vault_chunks_missing_dir_returns_empty(tmp_path: Path) -> None:
    assert corpus.load_vault_chunks(vault_dir=tmp_path / "absent") == []


def test_load_chunks_explicit_root_stays_hermetic(tmp_path: Path) -> None:
    (tmp_path / "RESEARCH_LOG.md").write_text("# Log\nbody")
    chunks = corpus.load_chunks(root=tmp_path)
    assert all(not c.source.startswith("vault:") for c in chunks)


def test_load_chunks_can_include_vault_with_explicit_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "wiki"
    vault.mkdir()
    (vault / "concept.md").write_text("# Concept\nvault passage")
    monkeypatch.setattr(corpus, "VAULT_DIR", vault)
    (tmp_path / "RESEARCH_LOG.md").write_text("# Log\nbody")
    chunks = corpus.load_chunks(root=tmp_path, include_vault=True)
    assert any(c.source == "vault:concept.md" for c in chunks)
