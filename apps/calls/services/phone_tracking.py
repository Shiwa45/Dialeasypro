"""
TeleCRM Backend — apps/calls/services/phone_tracking.py

Phone call tracking: the mobile app reads the phone's own call log and sends
every incoming and outgoing call here, so calls an agent makes or takes
outside the app's dialer reach the CRM too, and their recordings can follow.

Who is tracked:
    the company switch (Tenant.call_tracking_enabled, off by default)
    AND the agent's own switch (Agent.call_tracking_enabled, on by default)

A call reaches the server twice when the agent dials from the app: once when
they save the outcome (CallLogListCreateView), once from the phone's call log.
Whichever arrives second is merged into the first — never a second row:

* the phone's entry finds the app's call (same agent and number, start within
  MERGE_WINDOW) and returns it;
* the app's call finds the phone's entry and takes it over, adding the
  outcome, notes and lead.
"""
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.db import connection
from django.db.models import Q
from django.utils import timezone

from apps.core.constants import CallDirection
from apps.core.utils import normalize_indian_phone

logger = logging.getLogger(__name__)

#: Marks a call created from the phone's call log (CallLog.provider_meta).
SOURCE = "phone_call_log"

#: How far apart the app's and the phone's timestamps for one call can be.
#: The phone stamps the moment the call is placed; the app stamps the tap on
#: "Call", a few seconds earlier, and an outcome saved minutes later keeps
#: the dial time.
MERGE_WINDOW = timedelta(minutes=3)

#: Entries per request. The app sends what is new since its last sync; a
#: first sync after a long gap is paged by the app.
MAX_BATCH = 200

#: Older entries are not accepted: tracking starts when it is switched on,
#: not years back into the agent's personal history.
MAX_AGE = timedelta(days=7)

INCOMING, OUTGOING, MISSED, REJECTED, BLOCKED = "incoming", "outgoing", "missed", "rejected", "blocked"
CALL_TYPES = {INCOMING, OUTGOING, MISSED, REJECTED, BLOCKED}


# ============================================================
# Switches
# ============================================================

def current_tenant():
    from apps.tenants.models import Tenant

    return Tenant.objects.filter(schema_name=connection.schema_name).first()


def company_tracking_enabled(tenant=None) -> bool:
    tenant = tenant if tenant is not None else current_tenant()
    return bool(getattr(tenant, "call_tracking_enabled", False))


def tracking_enabled_for(agent, tenant=None) -> bool:
    """Whether this agent's phone calls are tracked."""
    if agent is None or not getattr(agent, "is_active", False):
        return False
    if not getattr(agent, "call_tracking_enabled", True):
        return False
    return company_tracking_enabled(tenant)


# ============================================================
# Matching
# ============================================================

def last10(number: str) -> str:
    digits = "".join(c for c in str(number or "") if c.isdigit())
    return digits[-10:]


def _same_number(qs, number: str):
    """Restrict a CallLog queryset to calls with this number (last 10 digits)."""
    tail = last10(number)
    if len(tail) < 7:
        return qs.filter(phone_number=number)
    return qs.filter(phone_number__endswith=tail)


def find_merge_candidate(agent, number: str, started_at, *, direction=None, from_phone=None):
    """
    The call already saved for this agent that this one duplicates, or None.

    from_phone=True: only calls that came from the phone's call log;
    False: only calls that did not; None: either.
    """
    from apps.calls.models import CallLog

    qs = CallLog.objects.filter(
        agent=agent,
        started_at__gte=started_at - MERGE_WINDOW,
        started_at__lte=started_at + MERGE_WINDOW,
    )
    if direction:
        qs = qs.filter(direction=direction)
    qs = _same_number(qs, number)
    if from_phone is True:
        qs = qs.filter(provider_meta__source=SOURCE)
    elif from_phone is False:
        qs = qs.exclude(provider_meta__source=SOURCE)
    # The closest in time.
    best, best_gap = None, None
    for call in qs[:10]:
        gap = abs((call.started_at - started_at).total_seconds())
        if best is None or gap < best_gap:
            best, best_gap = call, gap
    return best


def lead_for_number(agent, number: str):
    """The lead this agent may see with this number, most recently worked first."""
    from apps.leads.views import leads_visible_to

    if not number:
        return None
    qs = leads_visible_to(agent).filter(Q(phone=number) | Q(alternate_phone=number))
    from django.db.models import F

    return qs.order_by(F("last_contacted_at").desc(nulls_last=True), "-pk").first()


# ============================================================
# Sync
# ============================================================

class EntryError(ValueError):
    pass


def _parse_started(value):
    """Epoch milliseconds (what Android's call log stores) or an ISO string."""
    if isinstance(value, bool):
        raise EntryError("started_at is required.")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000.0, tz=dt_timezone.utc)
    if isinstance(value, str) and value.strip():
        from django.utils.dateparse import parse_datetime

        if value.strip().isdigit():
            return datetime.fromtimestamp(int(value) / 1000.0, tz=dt_timezone.utc)
        parsed = parse_datetime(value.strip())
        if parsed is None:
            raise EntryError("started_at is not a date.")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt_timezone.utc)
        return parsed
    raise EntryError("started_at is required.")


def clean_entry(raw) -> dict:
    """Validate one call-log entry from the phone. Raises EntryError."""
    if not isinstance(raw, dict):
        raise EntryError("Each call must be an object.")
    device_id = str(raw.get("device_id") or "").strip()[:30]
    if not device_id:
        raise EntryError("device_id is required.")
    call_type = str(raw.get("type") or "").strip().lower()
    if call_type not in CALL_TYPES:
        raise EntryError(f"Unknown call type: {call_type or '(none)'}.")
    started = _parse_started(raw.get("started_at"))
    now = timezone.now()
    if started > now + timedelta(minutes=10):
        raise EntryError("started_at is in the future.")
    if started < now - MAX_AGE:
        raise EntryError("Too old: only the last 7 days are synced.")
    try:
        duration = int(raw.get("duration_seconds") or 0)
    except (TypeError, ValueError):
        raise EntryError("duration_seconds must be a number.")
    duration = max(0, min(duration, 24 * 3600))

    raw_number = str(raw.get("number") or "").strip()
    number = normalize_indian_phone(raw_number)
    if not number:
        # Private/withheld numbers, service short codes: nothing to call back
        # and nothing to match a lead or a recording to.
        raise EntryError("No usable phone number (private or short code).")
    return {
        "device_id": device_id,
        "type": call_type,
        "started_at": started,
        "duration": duration,
        "number": number[:15],
    }


def direction_for(call_type: str, duration: int = 1) -> str:
    if call_type == OUTGOING:
        return CallDirection.OUTBOUND
    if call_type == INCOMING and duration > 0:
        return CallDirection.INBOUND
    return CallDirection.MISSED  # missed, rejected, blocked


def sync_entry(agent, entry: dict) -> dict:
    """
    Save one phone call-log entry. Returns
    {device_id, call_id, created, merged, needs_recording}.
    """
    from apps.calls.models import CallLog

    started = entry["started_at"]
    call_type = entry["type"]
    direction = direction_for(call_type, entry["duration"])
    connected = call_type in (INCOMING, OUTGOING) and entry["duration"] > 0
    client_call_id = f"phone-{entry['device_id']}-{int(started.timestamp())}"[:64]

    def result(call, created=False, merged=False):
        needs = bool(call.is_connected) and not hasattr_recording(call)
        return {
            "device_id": entry["device_id"],
            "call_id": str(call.pk),
            "created": created,
            "merged": merged,
            "needs_recording": needs,
            # Recorders name the file after the contact; the lead's name helps
            # the app match it.
            "lead_name": call.lead_label or "",
        }

    existing = CallLog.objects.filter(agent=agent, client_call_id=client_call_id).first()
    if existing is not None:
        return result(existing)
    # Already saved by the app's dialer (or a provider), or synced before
    # under another id: one call, one row.
    twin = find_merge_candidate(agent, entry["number"], started, direction=direction)
    if twin is not None:
        meta = dict(twin.provider_meta or {})
        if not meta.get("phone_device_id"):
            meta["phone_device_id"] = entry["device_id"]
            fields = ["provider_meta"]
            # The phone's call log has the real talk time; the app's own
            # figure can be an estimate.
            if connected and not twin.duration_seconds:
                twin.duration_seconds = entry["duration"]
                fields.append("duration_seconds")
            twin.provider_meta = meta
            twin.save(update_fields=fields)
        return result(twin, merged=True)

    lead = lead_for_number(agent, entry["number"])
    call = CallLog(
        agent=agent,
        lead=lead,
        direction=direction,
        phone_number=entry["number"],
        started_at=started,
        connected_at=started if connected else None,
        ended_at=started + timedelta(seconds=entry["duration"]),
        duration_seconds=entry["duration"] if connected else 0,
        is_connected=connected,
        client_call_id=client_call_id,
        provider_meta={"source": SOURCE, "call_type": call_type, "phone_device_id": entry["device_id"]},
    )
    call._actor = agent
    # An incoming call nobody answered is not an attempt by the agent: it must
    # not move the lead from New to Attempted or count as a dial. It is still
    # saved, so the missed call shows in the history.
    if direction != CallDirection.OUTBOUND and not connected:
        call._defer_outcome = True
    call.save()
    return result(call, created=True)


def hasattr_recording(call) -> bool:
    from apps.calls.models import CallRecording

    return CallRecording.objects.filter(call=call).exists()


def merge_app_call_into_phone_entry(agent, data: dict):
    """
    The app is saving a call the phone's call log already delivered: the
    phone's row, or None when there is none to take over.
    """
    number, started = data.get("phone_number"), data.get("started_at")
    if not number or not started:
        return None
    direction = data.get("direction") or CallDirection.OUTBOUND
    twin = find_merge_candidate(agent, number, started, direction=direction, from_phone=True)
    if twin is None or twin.disposition_id:
        return None
    return twin
