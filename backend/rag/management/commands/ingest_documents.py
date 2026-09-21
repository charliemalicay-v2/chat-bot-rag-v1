from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from rag.embedder import EmbeddingConfigError, active_model_name
from rag.ingest import ingest_directory


class Command(BaseCommand):
    help = "Chunk, embed and store the .md/.txt documents in a directory into the pgvector store."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=str(Path(settings.BASE_DIR) / "data" / "sample_docs"),
                            help="Directory to ingest (default: backend/data/sample_docs)")
        parser.add_argument("--reset", action="store_true", help="Delete ALL existing chunks first")

    def handle(self, *args, **opts):
        self.stdout.write(f"Embedding with {active_model_name()} (first run downloads the model)...")
        try:
            stats = ingest_directory(Path(opts["path"]), reset=opts["reset"])
        except (FileNotFoundError, EmbeddingConfigError) as exc:
            raise CommandError(str(exc)) from exc
        for rel in stats.skipped:
            self.stderr.write(f"skipped (empty or unreadable): {rel}")
        self.stdout.write(self.style.SUCCESS(f"Ingested {stats.files} file(s) into {stats.chunks} chunk(s)."))
