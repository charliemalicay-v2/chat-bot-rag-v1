from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import health as health_checks


@api_view(["GET"])
def live(request):
    """Process is up. Used by the container healthcheck (does not wait for the model pull)."""
    return Response({"status": "alive"})


@api_view(["GET"])
def health(request):
    results = health_checks.run_checks()
    ok = all(r["ok"] for r in results.values())
    return Response(
        {"status": "ok" if ok else "degraded", "checks": results},
        status=200 if ok else 503,
    )
