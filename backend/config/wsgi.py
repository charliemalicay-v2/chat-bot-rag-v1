import logging
import os
import threading

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()

logger = logging.getLogger(__name__)


def _warm_embedder():
    """Load the embedding model in the background so the first chat request is not slow.

    Runs only for the web worker (this module is imported by gunicorn), never for
    manage.py commands or tests. Failures are logged; requests will retry the load.
    """
    from django.conf import settings

    if settings.EMBEDDING_PROVIDER != "huggingface" or os.environ.get("RAG_SKIP_WARMUP") == "1":
        return

    def run():
        try:
            from rag.embedder import get_embedder

            get_embedder().embed_query("warm up")
            logger.info("Embedding model loaded in web worker")
        except Exception:  # noqa: BLE001
            logger.exception("Embedding warm-up failed; it will be retried on the first request")

    threading.Thread(target=run, name="embedder-warmup", daemon=True).start()


_warm_embedder()
