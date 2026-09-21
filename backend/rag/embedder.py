"""Embedding providers.

  huggingface  sentence-transformers model run in-process (default: BAAI/bge-small-en-v1.5)
  fake         deterministic hashed bag-of-words vectors; offline, for tests

All vectors are L2-normalised, so cosine distance and dot product agree.
Vectors from different models are NOT comparable. Every stored chunk records
`embedding_model`, and retrieval only searches rows made by the active model.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
from functools import lru_cache

from django.conf import settings

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


class EmbeddingConfigError(Exception):
    """Configured embedding model does not match the database schema."""


def resolve_query_prefix(model_name: str) -> str:
    """Prefix prepended to *queries only* (never to documents)."""
    configured = settings.EMBEDDING_QUERY_PREFIX
    if configured is not None:
        return configured
    # sentence-transformers ships an empty `query` prompt for BGE v1.5, so the
    # recommended retrieval instruction has to be added here.
    return BGE_QUERY_INSTRUCTION if "bge-" in model_name.lower() else ""


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        # Imported lazily: torch takes seconds to import and is not needed by tests.
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        # Renamed in sentence-transformers 6; keep the old name working for 5.x.
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = get_dim()
        self.query_prefix = resolve_query_prefix(model_name)
        # Serialise inference: one worker process serves several request threads.
        self._lock = threading.Lock()

    def _encode(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        with self._lock:
            arr = self._model.encode(
                texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=False
            )
        return [row.tolist() for row in arr]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts) if texts else []

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.query_prefix + text])[0]


class FakeEmbedder:
    """Hashed bag-of-words: texts sharing words get similar vectors. Deterministic."""

    def __init__(self, model_name: str = "fake-hash", dim: int | None = None):
        self.model_name = model_name
        self.dim = dim or settings.EMBEDDING_DIM

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            h = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big")
            v[h % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@lru_cache(maxsize=4)
def _build(provider: str, model_name: str):
    if provider == "fake":
        return FakeEmbedder()
    if provider == "huggingface":
        return SentenceTransformerEmbedder(model_name)
    raise EmbeddingConfigError(f"Unknown EMBEDDING_PROVIDER {provider!r} (expected 'huggingface' or 'fake')")


def get_embedder():
    """Process-wide singleton per (provider, model). Validates the vector size."""
    embedder = _build(settings.EMBEDDING_PROVIDER, settings.EMBEDDING_MODEL)
    if embedder.dim != settings.EMBEDDING_DIM:
        raise EmbeddingConfigError(
            f"{embedder.model_name} produces {embedder.dim}-dim vectors but the database column is "
            f"{settings.EMBEDDING_DIM}-dim. Set EMBEDDING_DIM to match and add a migration, or pick a "
            f"{settings.EMBEDDING_DIM}-dim model."
        )
    return embedder


def active_model_name() -> str:
    """Name stored in DocumentChunk.embedding_model for the active configuration."""
    return "fake-hash" if settings.EMBEDDING_PROVIDER == "fake" else settings.EMBEDDING_MODEL
