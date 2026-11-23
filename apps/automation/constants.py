"""
TeleCRM Backend — apps/automation/constants.py

What can start a workflow, what a workflow can do, and the states a run
moves through.
"""


class Trigger:
    LEAD_CREATED = "lead_created"
    LEAD_STATUS_CHANGED = "lead_status_changed"
    LEAD_ASSIGNED = "lead_assigned"
    CALL_CONNECTED = "call_connected"
    CALL_NOT_CONNECTED = "call_not_connected"
    CALL_OUTCOME = "call_outcome"
    WHATSAPP_RECEIVED = "whatsapp_received"
    FOLLOWUP_MISSED = "followup_missed"
    LEAD_INACTIVE = "lead_inactive"

    CHOICES = [
        (LEAD_CREATED, "Lead is created"),
        (LEAD_STATUS_CHANGED, "Lead status changes"),
        (LEAD_ASSIGNED, "Lead is assigned"),
        (CALL_CONNECTED, "Call is connected"),
        (CALL_NOT_CONNECTED, "Call is not connected"),
        (CALL_OUTCOME, "Call outcome is saved"),
        (WHATSAPP_RECEIVED, "WhatsApp message is received"),
        (FOLLOWUP_MISSED, "Follow-up is missed"),
        (LEAD_INACTIVE, "Lead has no activity"),
    ]

    DESCRIPTIONS = {
        LEAD_CREATED: "A new lead arrives — from the app, the web, an import form or an integration.",
        LEAD_STATUS_CHANGED: "A lead moves to (or from) the statuses you pick.",
        LEAD_ASSIGNED: "A lead gets an owner.",
        CALL_CONNECTED: "A call with the lead connects.",
        CALL_NOT_CONNECTED: "A call to the lead does not connect — no answer, busy, switched off.",
        CALL_OUTCOME: "An agent saves one of the call outcomes you pick.",
        WHATSAPP_RECEIVED: "The lead sends a WhatsApp message — optionally only with certain words (auto-reply).",
        FOLLOWUP_MISSED: "A follow-up is still open some time after it was due.",
        LEAD_INACTIVE: "An open lead has not been contacted for some days.",
    }

    #: Checked by a scan every few minutes rather than fired by an event.
    SCANNED = {FOLLOWUP_MISSED, LEAD_INACTIVE}


class Action:
    WAIT = "wait"
    SEND_WHATSAPP = "send_whatsapp"
    SEND_SMS = "send_sms"
    ASSIGN = "assign"
    CHANGE_STATUS = "change_status"
    CREATE_FOLLOWUP = "create_followup"
    ADD_NOTE = "add_note"
    NOTIFY = "notify"
    WEBHOOK = "webhook"

    CHOICES = [
        (WAIT, "Wait"),
        (SEND_WHATSAPP, "Send WhatsApp"),
        (SEND_SMS, "Send SMS"),
        (ASSIGN, "Assign lead"),
        (CHANGE_STATUS, "Change status"),
        (CREATE_FOLLOWUP, "Create follow-up"),
        (ADD_NOTE, "Add note"),
        (NOTIFY, "Notify agent"),
        (WEBHOOK, "Call webhook"),
    ]

    #: Steps that message the customer — held back during quiet hours.
    MESSAGING = {SEND_WHATSAPP, SEND_SMS}


class RunStatus:
    PENDING = "pending"        # created, about to run
    WAITING = "waiting"        # on a wait step or holding for quiet hours
    COMPLETED = "completed"
    CANCELLED = "cancelled"    # workflow switched off, lead deleted, or stopped by hand
    FAILED = "failed"          # the engine itself failed (a step failing is logged, not fatal)

    CHOICES = [
        (PENDING, "Pending"),
        (WAITING, "Waiting"),
        (COMPLETED, "Completed"),
        (CANCELLED, "Cancelled"),
        (FAILED, "Failed"),
    ]
    OPEN = (PENDING, WAITING)


class StepResult:
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"
    WAITING = "waiting"


#: Wait units → seconds.
WAIT_UNITS = {"minutes": 60, "hours": 3600, "days": 86400}

#: Longest a single wait may be.
MAX_WAIT_SECONDS = 90 * 86400

#: Most steps in one workflow.
MAX_STEPS = 20
