"""Embedding providers for the RAG pipeline.

The default provider is model2vec (static, CPU-only, no API key) so the feature
runs cold for anyone who clones the repo. A query and the corpus must always be
embedded by the same provider, so the active model name is stored alongside the
index and checked on read.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "minishlab/potion-base-8M"


class Embedder(Protocol):
    """Turns text into fixed-length float vectors."""

    @property
    def name(self) -> str:
        """Stable identifier for the model (stored with the index)."""
        ...

    @property
    def dim(self) -> int:
        """Embedding dimensionality."""
        ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors of length ``dim``."""
        ...


class Model2VecEmbedder:
    """Static-embedding provider backed by model2vec.

    Static embeddings are distilled from a transformer but require no torch and
    no network at inference time after the first download, which keeps the RAG
    feature reproducible on a laptop with no API key.
    """

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Load the static model.

        Args:
            model: model2vec model id on the Hugging Face hub.

        Raises:
            ImportError: If the optional ``rag`` extra is not installed.
        """
        try:
            from model2vec import StaticModel
        except ImportError as exc:  # pragma: no cover - exercised via extras
            raise ImportError(
                "RAG support requires the 'rag' extra. Install it with: uv sync --extra rag"
            ) from exc
        self._model_name = model
        self._model = StaticModel.from_pretrained(model)
        probe = self._model.encode(["dimension probe"])
        self._dim = int(probe.shape[1])
        logger.info("loaded embedder %s (dim=%d)", model, self._dim)

    @property
    def name(self) -> str:  # noqa: D102 - documented on the protocol
        return self._model_name

    @property
    def dim(self) -> int:  # noqa: D102 - documented on the protocol
        return self._dim

    def encode(self, texts: Sequence[str]) -> list[list[float]]:  # noqa: D102
        vectors = self._model.encode(list(texts))
        return [[float(x) for x in row] for row in vectors]
