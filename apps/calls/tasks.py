"""
TeleCRM Backend — apps/calls/tasks.py

Celery tasks for call management.
"""
import logging
from celery import shared_task
from apps.core.tasks import TenantAwareTask

logger = logging.getLogger(__name__)


@shared_task(base=TenantAwareTask, bind=True, max_retries=3)
def download_call_recording(self, schema_name: str, call_id: str, recording_url: str):
    """
    Download call recording from provider URL and store in S3.
    Called by provider webhook handlers after a call ends with a recording.
    """
    import requests
    from apps.calls.models import CallLog, CallRecording

    try:
        call = CallLog.objects.get(id=call_id)
    except CallLog.DoesNotExist:
        logger.warning(f"[Task] CallLog {call_id} not found in {schema_name}")
        return

    try:
        response = requests.get(recording_url, timeout=60)
        response.raise_for_status()

        from django.core.files.base import ContentFile
        content_type = response.headers.get("Content-Type", "audio/mpeg")
        ext = "mp3" if "mpeg" in content_type else "wav"
        filename = f"{call_id}.{ext}"

        recording, created = CallRecording.objects.get_or_create(
            call=call,
            defaults={"format": ext},
        )
        recording.file.save(filename, ContentFile(response.content), save=True)
        recording.file_size_bytes = len(response.content)
        recording.duration_seconds = call.duration_seconds
        recording.save(update_fields=["file_size_bytes", "duration_seconds"])

        logger.info(f"[Task] Recording saved for call {call_id}")

    except Exception as exc:
        logger.error(f"[Task] download_call_recording failed: {exc}")
        raise self.retry(exc=exc, countdown=120 * (self.request.retries + 1))


@shared_task(base=TenantAwareTask, bind=True)
def generate_call_report(self, schema_name: str, agent_id: int, date_str: str):
    """Generate daily call report for an agent. Called by performance summary dispatcher."""
    from django.db.models import Avg, Count, Q, Sum
    from apps.calls.models import CallLog

    calls = CallLog.objects.filter(
        agent_id=agent_id,
        started_at__date=date_str,
    )
    report = calls.aggregate(
        total=Count("id"),
        connected=Count("id", filter=Q(is_connected=True)),
        total_duration=Sum("duration_seconds"),
        avg_duration=Avg("duration_seconds", filter=Q(is_connected=True)),
    )
    return {
        "agent_id": agent_id,
        "date": date_str,
        "schema": schema_name,
        **report,
    }
