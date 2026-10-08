"""
The default call outcomes every tenant gets, and the upgrade from the old set.

Outcomes come in two groups. After a call the agent sees only the group that
matches the call status, so an unanswered call can no longer be given
"Connected – Interested".

`upgrade_dispositions` is used both by the data migration (historical models)
and by `manage.py seed_dispositions` (real models), so it only uses plain ORM
calls. It is safe to run again: it creates what is missing, renames the old
defaults in place (their calls keep the link), refreshes a default's rules only
where the tenant had left the old default value, and leaves outcomes a tenant
added alone apart from giving them a group.
"""
import re

CONNECTED = "connected"
NOT_CONNECTED = "not_connected"

# slug, name, category, lead_status, auto_followup_hours, is_positive, sets_dnd, sort_order
DEFAULTS = [
    # ---- Connected (the call was answered) -----------------------------
    ("interested", "Interested", CONNECTED, "interested", 24, True, False, 1),
    ("callback", "Call back later", CONNECTED, "follow_up", 4, True, False, 2),
    ("send_details", "Send details (WhatsApp / email)", CONNECTED, "follow_up", 24, True, False, 3),
    ("meeting_scheduled", "Meeting / visit / demo scheduled", CONNECTED, "negotiation", 24, True, False, 4),
    ("converted", "Sale done / Converted", CONNECTED, "converted", None, True, False, 5),
    ("not_interested", "Not interested", CONNECTED, "not_interested", None, False, False, 6),
    ("already_purchased", "Already purchased / not required", CONNECTED, "lost", None, False, False, 7),
    ("wrong_person", "Wrong person / wrong number", CONNECTED, "invalid", None, False, False, 8),
    ("dnd_request", "Asked not to call (DND)", CONNECTED, "lost", None, False, True, 9),
    ("language_barrier", "Language barrier", CONNECTED, "", None, False, False, 10),
    ("call_dropped", "Call dropped mid-conversation", CONNECTED, "", 1, False, False, 11),
    # ---- Not connected (the call was not answered) ---------------------
    ("no_answer", "Ringing, no answer", NOT_CONNECTED, "", 2, False, False, 21),
    ("busy", "Busy", NOT_CONNECTED, "", 1, False, False, 22),
    ("switched_off", "Switched off", NOT_CONNECTED, "", 6, False, False, 23),
    ("not_reachable", "Not reachable / out of coverage", NOT_CONNECTED, "", 4, False, False, 24),
    ("rejected", "Call rejected / cut", NOT_CONNECTED, "", 2, False, False, 25),
    ("invalid_number", "Invalid / out-of-service number", NOT_CONNECTED, "invalid", None, False, False, 26),
    ("voicemail", "Voicemail / IVR", NOT_CONNECTED, "", 24, False, False, 27),
]

FIELDS = ("slug", "name", "category", "lead_status", "auto_followup_hours", "is_positive", "sets_dnd", "sort_order")

# The previous default set: old slug -> (new slug, old values). A field is
# refreshed only where the tenant still has the old default value.
LEGACY = {
    "connected_interested": ("interested", {"name": "Connected – Interested", "lead_status": "interested",
                                            "auto_followup_hours": 24, "is_positive": True, "sort_order": 1}),
    "connected_callback": ("callback", {"name": "Connected – Callback Requested", "lead_status": "follow_up",
                                        "auto_followup_hours": 4, "is_positive": True, "sort_order": 2}),
    "connected_not_interested": ("not_interested", {"name": "Connected – Not Interested",
                                                    "lead_status": "not_interested", "auto_followup_hours": None,
                                                    "is_positive": False, "sort_order": 3}),
    "connected_purchased": ("already_purchased", {"name": "Connected – Already Purchased", "lead_status": "",
                                                  "auto_followup_hours": None, "is_positive": False,
                                                  "sort_order": 4}),
    "not_reachable": ("not_reachable", {"name": "Not Reachable", "lead_status": "", "auto_followup_hours": 6,
                                        "is_positive": False, "sort_order": 5}),
    "busy": ("busy", {"name": "Busy", "lead_status": "", "auto_followup_hours": 2, "is_positive": False,
                      "sort_order": 6}),
    "switched_off": ("switched_off", {"name": "Switched Off", "lead_status": "", "auto_followup_hours": 12,
                                      "is_positive": False, "sort_order": 7}),
    "wrong_number": ("wrong_person", {"name": "Wrong Number", "lead_status": "", "auto_followup_hours": None,
                                      "is_positive": False, "sort_order": 8}),
    "dnd": ("dnd_request", {"name": "Do Not Disturb", "lead_status": "", "auto_followup_hours": None,
                            "is_positive": False, "sort_order": 9}),
    "voicemail": ("voicemail", {"name": "Voicemail Left", "lead_status": "", "auto_followup_hours": 24,
                                "is_positive": False, "sort_order": 10}),
}

_NOT_CONNECTED_WORDS = re.compile(
    r"\b(not reachable|unreachable|busy|switched off|switch off|voicemail|voice mail|no answer|"
    r"not answered|not connected|ringing|rnr|no response|out of service|invalid number|"
    r"not lifted|call rejected|disconnected|cut the call|ivr)\b"
)


def guess_category(slug: str, name: str, marks_connected) -> str:
    """The group of an outcome a tenant added themselves."""
    if marks_connected is True:
        return CONNECTED
    if marks_connected is False:
        return NOT_CONNECTED
    text = f" {(slug or '').replace('_', ' ').replace('-', ' ')} {name or ''} ".lower()
    return NOT_CONNECTED if _NOT_CONNECTED_WORDS.search(text) else CONNECTED


def upgrade_dispositions(CallDisposition) -> dict:
    """Bring one tenant's outcomes up to the current default set."""
    defaults = {row[0]: dict(zip(FIELDS, row)) for row in DEFAULTS}
    renamed = created = 0

    # 1. Old defaults: rename in place, refresh untouched values.
    for old_slug, (new_slug, old_values) in LEGACY.items():
        row = CallDisposition.objects.filter(slug=old_slug).first()
        if row is None:
            continue
        new = defaults[new_slug]
        updates = {}
        if new_slug != old_slug and not CallDisposition.objects.filter(slug=new_slug).exists():
            updates["slug"] = new_slug
            renamed += 1
        elif new_slug != old_slug:
            # The new slug is taken already; keep this one as a tenant outcome.
            CallDisposition.objects.filter(pk=row.pk).update(
                category=new["category"], marks_connected=new["category"] == CONNECTED,
            )
            continue
        for field, old_value in old_values.items():
            if getattr(row, field) == old_value:
                updates[field] = new[field]
        updates.update(
            category=new["category"], marks_connected=new["category"] == CONNECTED,
            is_system=True, sets_dnd=new["sets_dnd"],
        )
        CallDisposition.objects.filter(pk=row.pk).update(**updates)

    # 2. Defaults that are missing. A default already present (seeded with
    #    the new slug) only gets its group and system flag.
    for slug, new in defaults.items():
        row = CallDisposition.objects.filter(slug=slug).first()
        if row is not None:
            CallDisposition.objects.filter(pk=row.pk).update(
                category=new["category"], marks_connected=new["category"] == CONNECTED,
                is_system=True,
            )
            continue
        if CallDisposition.objects.filter(name__iexact=new["name"]).exists():
            continue  # the tenant has their own outcome by that name
        CallDisposition.objects.create(
            slug=slug, name=new["name"], category=new["category"],
            marks_connected=new["category"] == CONNECTED,
            lead_status=new["lead_status"], auto_followup_hours=new["auto_followup_hours"],
            is_positive=new["is_positive"], sets_dnd=new["sets_dnd"], sort_order=new["sort_order"],
            is_system=True, is_active=True,
        )
        created += 1

    # 3. The tenant's own outcomes get a group.
    for row in CallDisposition.objects.filter(is_system=False):
        category = guess_category(row.slug, row.name, row.marks_connected)
        CallDisposition.objects.filter(pk=row.pk).update(
            category=category, marks_connected=category == CONNECTED,
        )

    return {"renamed": renamed, "created": created}
