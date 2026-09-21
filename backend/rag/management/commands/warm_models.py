from django.core.management.base import BaseCommand

from rag.embedder import get_embedder


class Command(BaseCommand):
    help = "Download and load the embedding model so the first real request is fast."

    def handle(self, *args, **opts):
        embedder = get_embedder()
        embedder.embed_query("warm up")
        self.stdout.write(f"[embedder] {embedder.model_name} ready ({embedder.dim} dims)")
