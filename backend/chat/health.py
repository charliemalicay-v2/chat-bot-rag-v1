"""Dependency checks behind GET /api/health/. Each check returns (ok, detail)."""

from django.db import connections


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


CHECKS = {
    "mysql": check_mysql,
    "vector_db": check_vector_db,
}


def run_checks():
    results = {}
    for name, fn in CHECKS.items():
        ok, detail = fn()
        results[name] = {"ok": ok, "detail": detail}
    return results
