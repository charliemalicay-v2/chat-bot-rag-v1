from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


class DocumentChunk(models.Model):
    """A chunk of an ingested document plus its embedding. Lives in the pgvector DB.

    Source fields are stored on the row itself: there is no cross-database FK.
    """

    source_title = models.CharField(max_length=300)
    source_path = models.CharField(max_length=500)
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    embedding = VectorField(dimensions=settings.EMBEDDING_DIM)
    # Vectors from different models are not comparable; record which one made this row.
    embedding_model = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["source_path", "chunk_index"], name="uniq_source_chunk"),
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.source_title}#{self.chunk_index}"
