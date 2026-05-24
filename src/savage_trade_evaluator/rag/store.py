"""DuckDB-backed HNSW vector store for the research corpus.

Keeps the project's single-store philosophy: the index is a DuckDB file with a
``vss`` HNSW index over the chunk embeddings. Cosine distance is used for
ranking. The active embedding model name is stored in a sidecar table so a
query is never embedded by a different model than the corpus.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb

from savage_trade_evaluator.config import DATA_DIR
from savage_trade_evaluator.rag import corpus
from savage_trade_evaluator.rag.embed import Embedder

logger = logging.getLogger(__name__)

RAG_DB_PATH = DATA_DIR / "duckdb" / "research_rag.db"
_BATCH = 256


@dataclass(frozen=True)
class Hit:
    """A retrieved chunk and its similarity to the query.

    Attributes:
        source: Corpus file the chunk came from.
        heading: Heading trail locating the chunk in that file.
        text: The chunk text.
        score: Cosine similarity in [0, 1]; higher is closer.
    """

    source: str
    heading: str
    text: str
    score: float


def _connect(path: Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection with the ``vss`` extension loaded.

    Args:
        path: Database file path.
        read_only: Open read-only (for queries).

    Returns:
        An open connection with HNSW persistence enabled.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path), read_only=read_only)
    conn.execute("INSTALL vss")
    conn.execute("LOAD vss")
    # Required to persist an HNSW index inside a file-backed database.
    conn.execute("SET hnsw_enable_experimental_persistence = true")
    return conn


def build_index(embedder: Embedder, path: Path | None = None) -> int:
    """Build the vector index from the corpus, replacing any existing one.

    Args:
        embedder: Provider used to embed every chunk.
        path: Index database path. Defaults to ``RAG_DB_PATH``.

    Returns:
        The number of chunks indexed.
    """
    target = path or RAG_DB_PATH
    chunks = corpus.load_chunks()
    dim = embedder.dim
    conn = _connect(target)
    try:
        conn.execute("DROP INDEX IF EXISTS rag_chunks_hnsw")
        conn.execute("DROP TABLE IF EXISTS rag_chunks")
        conn.execute("DROP TABLE IF EXISTS rag_meta")
        conn.execute(
            f"CREATE TABLE rag_chunks ("
            f"  id INTEGER, source VARCHAR, heading VARCHAR, text VARCHAR,"
            f"  embedding FLOAT[{dim}])"
        )
        for start in range(0, len(chunks), _BATCH):
            batch = chunks[start : start + _BATCH]
            vectors = embedder.encode([c.text for c in batch])
            conn.executemany(
                "INSERT INTO rag_chunks VALUES (?, ?, ?, ?, ?)",
                [
                    [start + i, c.source, c.heading, c.text, vec]
                    for i, (c, vec) in enumerate(zip(batch, vectors, strict=True))
                ],
            )
        conn.execute(
            "CREATE INDEX rag_chunks_hnsw ON rag_chunks "
            "USING HNSW (embedding) WITH (metric = 'cosine')"
        )
        conn.execute("CREATE TABLE rag_meta (model VARCHAR, dim INTEGER, chunks INTEGER)")
        conn.execute("INSERT INTO rag_meta VALUES (?, ?, ?)", [embedder.name, dim, len(chunks)])
        logger.info("indexed %d chunks (model=%s, dim=%d)", len(chunks), embedder.name, dim)
        return len(chunks)
    finally:
        conn.close()


def search(embedder: Embedder, query: str, k: int = 5, path: Path | None = None) -> list[Hit]:
    """Retrieve the ``k`` chunks most similar to ``query``.

    Args:
        embedder: Provider used to embed the query. Must match the index model.
        query: Natural-language question.
        k: Number of hits to return.
        path: Index database path. Defaults to ``RAG_DB_PATH``.

    Returns:
        Hits ordered by descending similarity.

    Raises:
        FileNotFoundError: If the index has not been built yet.
        ValueError: If the query embedder differs from the indexed model.
    """
    target = path or RAG_DB_PATH
    if not target.exists():
        raise FileNotFoundError(
            f"No RAG index at {target}. Build it first with: ste research index"
        )
    conn = _connect(target, read_only=True)
    try:
        indexed_model = conn.execute("SELECT model FROM rag_meta").fetchone()
        if indexed_model and indexed_model[0] != embedder.name:
            raise ValueError(
                f"Index was built with '{indexed_model[0]}' but query uses "
                f"'{embedder.name}'. Rebuild with: ste research index"
            )
        qvec = embedder.encode([query])[0]
        rows = conn.execute(
            "SELECT source, heading, text, "
            "       1 - array_cosine_distance(embedding, ?::FLOAT[" + str(embedder.dim) + "]) "
            "         AS score "
            "FROM rag_chunks "
            "ORDER BY array_cosine_distance(embedding, ?::FLOAT[" + str(embedder.dim) + "]) "
            "LIMIT ?",
            [qvec, qvec, k],
        ).fetchall()
        return [Hit(source=r[0], heading=r[1], text=r[2], score=float(r[3])) for r in rows]
    finally:
        conn.close()
