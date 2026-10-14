"""
Drop filter values a calling queue can never match.

Queue filters used to be saved as sent, so existing queues may hold closed
statuses (a queue never serves those), sources or priorities that no longer
exist (e.g. "other"), or a lock time of 0 minutes. The API now refuses all of
these, so a queue holding one could not be saved again from the screen.
"""
from django.db import migrations

STATUSES = {"new", "attempted", "contacted", "interested", "follow_up", "negotiation"}
PRIORITIES = {"hot", "warm", "cold"}
SOURCES = {
    "indiamart", "meta_facebook", "meta_instagram", "meta_ctwa", "99acres", "housing_com",
    "magicbricks", "justdial", "sulekha", "tradeindia", "google_ads", "website", "webhook",
    "manual", "csv_import", "api", "whatsapp", "referral",
}


def clean(apps, schema_editor):
    CallQueue = apps.get_model("leads", "CallQueue")
    for q in CallQueue.objects.all():
        def keep(values, allowed):
            out = []
            for v in values or []:
                key = str(v).strip().lower()
                if key in allowed and key not in out:
                    out.append(key)
            return out

        changed = {
            "filter_statuses": keep(q.filter_statuses, STATUSES),
            "filter_priorities": keep(q.filter_priorities, PRIORITIES),
            "filter_sources": keep(q.filter_sources, SOURCES),
            "filter_tags": [t.strip() for t in (q.filter_tags or []) if isinstance(t, str) and t.strip()],
            "lock_ttl_minutes": min(max(q.lock_ttl_minutes or 30, 1), 480),
            "redial_cooldown_hours": min(q.redial_cooldown_hours, 720),
        }
        if any(getattr(q, k) != v for k, v in changed.items()):
            for k, v in changed.items():
                setattr(q, k, v)
            q.save(update_fields=list(changed))


class Migration(migrations.Migration):

    dependencies = [("leads", "0010_backfill_call_summary")]

    operations = [migrations.RunPython(clean, migrations.RunPython.noop)]
