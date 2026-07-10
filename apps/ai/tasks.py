"""
TeleCRM Backend — apps/ai/tasks.py

Both tasks are per-tenant and self-gating: a tenant whose plan doesn't include
the relevant AI feature is a no-op, so the recording-upload view can enqueue
unconditionally without knowing anything about entitlements.

Pipeline:  recording uploaded → transcribe_call → analyse_call
"""
import logging

from celery import shared_task
from django.utils import timezone

from apps.ai.constants import InsightStatus, TranscriptStatus
from apps.core.tasks import TenantAwareTask

logger = logging.getLogger(__name__)


def _tenant_has(schema_name: str, feature_key: str) -> bool:
    from apps.core.middleware import TenantFeatureFlagMiddleware
    from apps.tenants.models import Tenant

    try:
        tenant = Tenant.objects.get(schema_name=schema_name)
    except Tenant.DoesNotExist:
        return False
    mw = TenantFeatureFlagMiddleware(lambda r: None)
    return bool(mw._get_tenant_features(tenant).get(feature_key, False))


@shared_task(base=TenantAwareTask, bind=True, max_retries=3, default_retry_delay=300)
def transcribe_call(self, schema_name, call_id):
    """Transcribe one call's recording, then hand off to analysis."""
    from apps.ai.services import transcription
    from apps.calls.models import CallRecording
    from apps.core.constants import FeatureKey

    if not _tenant_has(schema_name, FeatureKey.AI_CALL_TRANSCRIPTION):
        return {"skipped": "feature_not_enabled"}
    if not transcription.is_enabled():
        return {"skipped": "no_asr_provider_configured"}

    recording = CallRecording.objects.filter(call_id=call_id).first()
    if recording is None:
        return {"skipped": "no_recording"}
    if recording.transcript_status == TranscriptStatus.DONE and recording.transcript:
        # Already transcribed — re-running would just burn ASR minutes.
        analyse_call.delay(schema_name, str(call_id))
        return {"skipped": "already_transcribed"}

    recording.transcript_status = TranscriptStatus.PROCESSING
    recording.save(update_fields=["transcript_status"])

    try:
        result = transcription.transcribe(recording)
    except transcription.TranscriptionUnavailable as exc:
        # Misconfiguration, not a bad recording. Leave it pending so a later
        # run picks it up once the provider is wired in.
        recording.transcript_status = TranscriptStatus.PENDING
        recording.save(update_fields=["transcript_status"])
        logger.warning("[ai] transcription unavailable for %s: %s", call_id, exc)
        return {"skipped": "no_asr_provider_configured"}
    except Exception as exc:
        recording.transcript_status = TranscriptStatus.FAILED
        recording.transcript_error = str(exc)[:500]
        recording.save(update_fields=["transcript_status", "transcript_error"])
        logger.error("[ai] transcription failed for call %s: %s", call_id, exc)
        raise self.retry(exc=exc)

    recording.transcript = result["text"]
    recording.transcript_language = result["language"]
    recording.transcript_provider = result["provider"]
    recording.transcript_status = TranscriptStatus.DONE
    recording.transcript_error = ""
    recording.transcribed_at = timezone.now()
    recording.save(update_fields=[
        "transcript", "transcript_language", "transcript_provider",
        "transcript_status", "transcript_error", "transcribed_at",
    ])

    analyse_call.delay(schema_name, str(call_id))
    return {"transcribed": True, "chars": len(result["text"])}


@shared_task(base=TenantAwareTask, bind=True, max_retries=3, default_retry_delay=300)
def analyse_call(self, schema_name, call_id):
    """Run Claude over an existing transcript and store the insight."""
    from apps.ai.models import CallInsight
    from apps.ai.services import insights
    from apps.calls.models import CallDisposition, CallLog
    from apps.core.constants import FeatureKey

    if not _tenant_has(schema_name, FeatureKey.AI_CALL_INSIGHTS):
        return {"skipped": "feature_not_enabled"}
    if not insights.is_enabled():
        return {"skipped": "no_api_key_configured"}

    call = (
        CallLog.objects
        .select_related("lead", "recording")
        .filter(pk=call_id)
        .first()
    )
    if call is None:
        return {"skipped": "no_call"}

    recording = getattr(call, "recording", None)
    if recording is None or not recording.transcript:
        return {"skipped": "no_transcript"}

    insight, _ = CallInsight.objects.get_or_create(call=call)
    insight.status = InsightStatus.PROCESSING
    insight.save(update_fields=["status"])

    dispositions = {
        d.slug: d for d in CallDisposition.objects.filter(is_active=True)
    }

    try:
        result = insights.analyse(
            recording.transcript,
            disposition_slugs=list(dispositions),
            meta={
                "direction": call.direction,
                "duration_seconds": call.duration_seconds,
                "lead_name": getattr(call.lead, "name", None),
            },
        )
    except insights.TranscriptTooShort as exc:
        insight.status = InsightStatus.SKIPPED
        insight.error = str(exc)[:500]
        insight.save(update_fields=["status", "error"])
        return {"skipped": "transcript_too_short"}
    except insights.InsightUnavailable as exc:
        insight.status = InsightStatus.PENDING
        insight.save(update_fields=["status"])
        logger.warning("[ai] insights unavailable for %s: %s", call_id, exc)
        return {"skipped": "no_api_key_configured"}
    except Exception as exc:
        insight.status = InsightStatus.FAILED
        insight.error = str(exc)[:500]
        insight.save(update_fields=["status", "error"])
        logger.error("[ai] insight failed for call %s: %s", call_id, exc)
        raise self.retry(exc=exc)

    suggested = result.pop("suggested_disposition", "")
    for field, value in result.items():
        setattr(insight, field, value)
    insight.suggested_disposition = dispositions.get(suggested)
    insight.status = InsightStatus.DONE
    insight.error = ""
    insight.generated_at = timezone.now()
    insight.save()

    return {"analysed": True, "sentiment": insight.sentiment}


@shared_task(base=TenantAwareTask, bind=True)
def backfill_transcripts(self, schema_name, limit=50):
    """
    Transcribe recordings that were uploaded before the tenant bought the AI
    module (or while the ASR provider was down). Newest first — recent calls
    are the ones a manager actually reviews.
    """
    from apps.calls.models import CallRecording

    pending = list(
        CallRecording.objects
        .filter(transcript_status__in=[TranscriptStatus.PENDING, TranscriptStatus.FAILED])
        # Keep rows that have audio in at least one of the two stores.
        .exclude(cloud_url="", file="")
        .order_by("-uploaded_at")
        .values_list("call_id", flat=True)[:limit]
    )
    for call_id in pending:
        transcribe_call.delay(schema_name, str(call_id))
    return {"queued": len(pending)}
