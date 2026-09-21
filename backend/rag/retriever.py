"""Similarity search over ingested document chunks (pgvector, cosine distance)."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from pgvector.django import CosineDistance

from .embedder import active_model_name, get_embedder
from .models import DocumentChunk


@dataclass(frozen=True)
class RetrievedChunk:
    id: int
    source_title: str
    source_path: str
    chunk_index: int
    content: str
    distance: float  # cosine distance: 0 = identical direction, 2 = opposite


def search_chunks(query: str, k: int | None = None, max_distance: float | None = None) -> list[RetrievedChunk]:
    """Top-k chunks closest to `query`, optionally dropping anything farther than `max_distance`.

    Only rows embedded by the *active* model are searched; vectors from a
    different model live in a different space and would give meaningless ranks.
    """
    k = k or settings.RAG_TOP_K
    query_vec = get_embedder().embed_query(query)
    rows = (
        DocumentChunk.objects.filter(embedding_model=active_model_name())
        .annotate(distance=CosineDistance("embedding", query_vec))
        .order_by("distance")[:k]
    )
    results = [
        RetrievedChunk(r.id, r.source_title, r.source_path, r.chunk_index, r.content, float(r.distance))
        for r in rows
    ]
    if max_distance is not None:
        results = [r for r in results if r.distance <= max_distance]
    return results
