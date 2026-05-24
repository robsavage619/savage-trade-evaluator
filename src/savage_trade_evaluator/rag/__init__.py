"""Retrieval-augmented generation over the project's own research corpus.

A small, production-shaped RAG pipeline: ingest markdown → chunk → embed →
index in a DuckDB HNSW vector store → retrieve with provenance → optionally
synthesise a grounded, cited answer. Retrieval always precedes generation;
the generator never answers without retrieved context.
"""

from __future__ import annotations
