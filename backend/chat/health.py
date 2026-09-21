"""Dependency checks behind GET /api/health/. Each check returns (ok, detail)."""

import httpx
from django.conf import settings
from django.db import connections

from rag.llm import normalize_host


def check_mysql():
    try:
        with connections["default"].cursor() as cur:
            cur.execute("SELECT VERSION()")
            return True, f"mysql {cur.fetchone()[0]}"
    except Exception as exc:  # noqa: BLE001 - report any failure, never raise
        return False, str(exc)


def check_vector_db():
    try:
        with connections["vector"].cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cur.fetchone()
        if row is None:
            return False, "pgvector extension is not enabled"
        return True, f"pgvector {row[0]}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def check_llm():
    if settings.LLM_PROVIDER != "ollama":
        return True, f"{settings.LLM_PROVIDER} provider (no server needed)"
    base = normalize_host(settings.OLLAMA_HOST)
    try:
        resp = httpx.get(f"{base}/api/tags", timeout=3.0)
        resp.raise_for_status()
        names = {m.get("name") for m in resp.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001
        return False, f"ollama not reachable at {base}: {exc}"
    wanted = settings.OLLAMA_MODEL
    if ":" not in wanted:
        wanted += ":latest"
    if wanted not in names:
        return False, f"model {settings.OLLAMA_MODEL} not available yet (first start pulls it; watch the backend logs)"
    return True, f"ollama model {settings.OLLAMA_MODEL} ready"


CHECKS = {
    "mysql": check_mysql,
    "vector_db": check_vector_db,
    "llm": check_llm,
}


def run_checks():
    results = {}
    for name, fn in CHECKS.items():
        ok, detail = fn()
        results[name] = {"ok": ok, "detail": detail}
    return results
