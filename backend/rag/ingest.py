"""Load text documents from a directory into the vector store."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction

from .chunker import chunk_text, extract_title
from .embedder import active_model_name, get_embedder
from .models import DocumentChunk

SUPPORTED_SUFFIXES = {".md", ".txt"}


@dataclass
class IngestStats:
    files: int = 0
    chunks: int = 0
    skipped: list[str] = field(default_factory=list)  # unreadable or empty files


def ingest_directory(root: Path, reset: bool = False) -> IngestStats:
    """Chunk, embed and store every .md/.txt file under `root`.

    Re-running is safe: a file's existing chunks are replaced (delete + insert in
    one transaction), so edited documents never leave stale chunks behind.
    `reset=True` first empties the whole store (also drops rows from other models).
    """
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Not a directory: {root}")

    embedder = get_embedder()
    model_name = active_model_name()
    stats = IngestStats()

    if reset:
        DocumentChunk.objects.all().delete()

    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    for path in files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            stats.skipped.append(rel)
            continue
        chunks = chunk_text(text, settings.CHUNK_WORDS, settings.CHUNK_OVERLAP_WORDS)
        if not chunks:
            stats.skipped.append(rel)
            continue

        title = extract_title(text, path.stem.replace("-", " ").replace("_", " ").title())
        vectors = embedder.embed_documents(chunks)
        rows = [
            DocumentChunk(
                source_title=title, source_path=rel, chunk_index=i,
                content=content, embedding=vec, embedding_model=model_name,
            )
            for i, (content, vec) in enumerate(zip(chunks, vectors))
        ]
        with transaction.atomic(using="vector"):
            DocumentChunk.objects.filter(source_path=rel).delete()
            DocumentChunk.objects.bulk_create(rows)
        stats.files += 1
        stats.chunks += len(rows)
    return stats
