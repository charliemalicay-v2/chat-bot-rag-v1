-- Enables the pgvector extension on first initialisation of the data volume.
-- The Django migration (pgvector.django.VectorExtension) is idempotent and
-- also enables it, so this file is a safety net rather than the only path.
CREATE EXTENSION IF NOT EXISTS vector;
