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


def _mark_insight(call_id, status: str, error: str = "") -> None:
    """
    Keep the call's summary row in step with the pipeline.

    A recorded call had no row at all until analysis finished, so the AI
    Call Summary screen showed nothing — not "waiting", not "failed" — while
    recordings sat untranscribed (for want of an API key, or because the
    audio was in a format Gemini can't read).
    """
    from apps.ai.models import CallInsight

    insight, _ = CallInsight.objects.get_or_create(call_id=call_id)
    if insight.status == InsightStatus.DONE and status != InsightStatus.DONE:
        # A finished summary is kept while a re-run is in flight.
        return
    insight.status = status
    insight.error = error[:500]
    insight.save(update_fields=["status", "error", "updated_at"])


@shared_task(base=TenantAwareTask, bind=True, max_retries=3, default_retry_delay=300)
def transcribe_call(self, schema_name, call_id, force=False):
    """Transcribe one call's recording, then hand off to analysis."""
    from apps.ai.services import transcription
    from apps.calls.models import CallRecording
    from apps.core.constants import FeatureKey

    if not _tenant_has(schema_name, FeatureKey.AI_CALL_TRANSCRIPTION):
        return {"skipped": "feature_not_enabled"}

    recording = CallRecording.objects.filter(call_id=call_id).first()
    if recording is None:
        return {"skipped": "no_recording"}

    if not transcription.is_enabled():
        _mark_insight(call_id, InsightStatus.PENDING,
                      "Waiting for the server's GEMINI_API_KEY to be set.")
        return {"skipped": "no_api_key_configured"}

    if not force and recording.transcript_status == TranscriptStatus.DONE and recording.transcript:
        # Already transcribed — re-running would just burn audio tokens.
        analyse_call.delay(schema_name, str(call_id))
        return {"skipped": "already_transcribed"}

    recording.transcript_status = TranscriptStatus.PROCESSING
    recording.save(update_fields=["transcript_status"])
    _mark_insight(call_id, InsightStatus.PROCESSING)

    try:
        result = transcription.transcribe(recording)
    except transcription.TranscriptionUnavailable as exc:
        # Misconfiguration, not a bad recording. Leave it pending so a later
        # run picks it up once GEMINI_API_KEY is set.
        recording.transcript_status = TranscriptStatus.PENDING
        recording.save(update_fields=["transcript_status"])
        _mark_insight(call_id, InsightStatus.PENDING,
                      "Waiting for the server's GEMINI_API_KEY to be set.")
        logger.warning("[ai] transcription unavailable for %s: %s", call_id, exc)
        return {"skipped": "no_api_key_configured"}
    except transcription.PERMANENT_ERRORS as exc:
        # No speech, an unreadable file: retrying used to repeat the paid
        # request three more times and fail the same way.
        recording.transcript_status = TranscriptStatus.FAILED
        recording.transcript_error = str(exc)[:500]
        recording.save(update_fields=["transcript_status", "transcript_error"])
        status = (InsightStatus.SKIPPED if isinstance(exc, transcription.NoSpeech)
                  else InsightStatus.FAILED)
        _mark_insight(call_id, status, str(exc))
        logger.info("[ai] call %s not transcribable: %s", call_id, exc)
        return {"skipped": "not_transcribable", "reason": str(exc)[:200]}
    except Exception as exc:
        recording.transcript_status = TranscriptStatus.FAILED
        recording.transcript_error = str(exc)[:500]
        recording.save(update_fields=["transcript_status", "transcript_error"])
        _mark_insight(call_id, InsightStatus.FAILED, f"Transcription failed: {exc}")
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
    """Run Gemini over an existing transcript and store the insight."""
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
        d.slug: d for d in CallDisposition.objects.filter(is_active=True, category="connected")
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
    except insights.InsightRequestFailed as exc:
        insight.status = InsightStatus.FAILED
        insight.error = str(exc)[:500]
        insight.save(update_fields=["status", "error"])
        logger.error("[ai] insight request failed for call %s: %s", call_id, exc)
        raise self.retry(exc=exc)
    except insights.GeminiError as exc:
        # A runaway transcript, a blocked prompt: the same input fails the
        # same way, so it is not retried (each retry is a paid request).
        insight.status = InsightStatus.FAILED
        insight.error = str(exc)[:500]
        insight.save(update_fields=["status", "error"])
        logger.error("[ai] insight failed for call %s: %s", call_id, exc)
        return {"failed": str(exc)[:200]}
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
    module (or while Gemini was unreachable). Newest first — recent calls
    are the ones a manager actually reviews.
    """
    from apps.calls.models import CallRecording

    pending = list(
        CallRecording.objects
        # Stuck "processing" rows too: a worker killed mid-run left them there
        # for good, and nothing else would ever pick them up again.
        .filter(transcript_status__in=[
            TranscriptStatus.PENDING, TranscriptStatus.FAILED, TranscriptStatus.PROCESSING,
        ])
        # Keep rows that have audio in at least one of the two stores.
        .exclude(cloud_url="", file="")
        .order_by("-uploaded_at")
        .values_list("call_id", flat=True)[:limit]
    )
    for call_id in pending:
        transcribe_call.delay(schema_name, str(call_id))
    return {"queued": len(pending)}
