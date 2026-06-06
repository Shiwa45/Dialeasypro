"""
TeleCRM Backend — apps/core/views.py

Core utility views.

HealthCheckView — used by load balancers, uptime monitoring, and Docker healthchecks.
Returns 200 OK with service status when all dependencies are healthy.
Returns 503 when any critical dependency is down.
"""
import logging
import time

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

logger = logging.getLogger(__name__)


class HealthCheckView(View):
    """
    Health check endpoint for infrastructure monitoring.

    GET /health/ → 200 OK if healthy, 503 if degraded

    Response:
    {
      "status": "healthy",       ← or "degraded"
      "timestamp": "...",
      "services": {
        "database": "ok",        ← or "error: ..."
        "redis": "ok",
        "celery": "ok"           ← "unknown" if can't check
      },
      "version": "1.0.0"
    }
    """

    def get(self, request, *args, **kwargs):
        services = {}
        overall_healthy = True

        # ---- Check PostgreSQL ----------------------------------
        db_status = self._check_database()
        services["database"] = db_status
        if db_status != "ok":
            overall_healthy = False

        # ---- Check Redis --------------------------------------
        redis_status = self._check_redis()
        services["redis"] = redis_status
        if redis_status != "ok":
            overall_healthy = False

        # ---- Check Celery (non-critical — don't fail health) --
        services["celery"] = self._check_celery()

        response_data = {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": timezone.now().isoformat(),
            "services": services,
            "version": "1.0.0",
        }

        status_code = 200 if overall_healthy else 503
        return JsonResponse(response_data, status=status_code)

    def _check_database(self) -> str:
        """Verify PostgreSQL is reachable with a cheap query."""
        try:
            start = time.monotonic()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return f"ok ({elapsed_ms}ms)"
        except Exception as exc:
            logger.error(f"[HealthCheck] Database error: {exc}")
            return f"error: {str(exc)[:100]}"

    def _check_redis(self) -> str:
        """Verify Redis is reachable."""
        try:
            from django.core.cache import cache
            start = time.monotonic()
            cache.set("health_check_ping", "pong", timeout=10)
            result = cache.get("health_check_ping")
            elapsed_ms = int((time.monotonic() - start) * 1000)
            if result == "pong":
                return f"ok ({elapsed_ms}ms)"
            return "error: ping/pong mismatch"
        except Exception as exc:
            logger.error(f"[HealthCheck] Redis error: {exc}")
            return f"error: {str(exc)[:100]}"

    def _check_celery(self) -> str:
        """
        Check if Celery workers are alive.
        Non-blocking — uses ping with a very short timeout.
        """
        try:
            from config.celery import app as celery_app
            inspector = celery_app.control.inspect(timeout=1)
            active_workers = inspector.active()
            if active_workers:
                count = len(active_workers)
                return f"ok ({count} worker{'s' if count != 1 else ''})"
            return "no workers"
        except Exception:
            return "unknown"
