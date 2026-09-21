from django.core.management.base import BaseCommand, CommandError

from rag.embedder import EmbeddingConfigError
from rag.retriever import search_chunks


class Command(BaseCommand):
    help = "Run a similarity search against the vector store (no LLM involved). Use it to debug retrieval."

    def add_arguments(self, parser):
        parser.add_argument("query", nargs="+")
        parser.add_argument("-k", type=int, default=None, help="Number of results (default: RAG_TOP_K)")

    def handle(self, *args, **opts):
        query = " ".join(opts["query"])
        try:
            results = search_chunks(query, k=opts["k"])
        except EmbeddingConfigError as exc:
            raise CommandError(str(exc)) from exc
        if not results:
            self.stdout.write("No chunks found. Did you run: python manage.py ingest_documents ?")
            return
        for rank, r in enumerate(results, 1):
            snippet = " ".join(r.content.split())[:160]
            self.stdout.write(f"{rank}. dist={r.distance:.4f}  {r.source_title} [{r.source_path}#{r.chunk_index}]")
            self.stdout.write(f"   {snippet}...")
