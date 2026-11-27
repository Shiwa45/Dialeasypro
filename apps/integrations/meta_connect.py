"""
TeleCRM Backend — apps/integrations/meta_connect.py

Meta Lead Ads through "Continue with Facebook".

Before this a tenant had to create their own Meta app, find a Page token,
paste it with a Page id, an app secret and a verify token, and register a
webhook in Meta's developer portal. Few finished that, so leads arrived only
when someone pressed "Sync now".

Now the platform owns one Meta app (settings.META_APP_ID / META_APP_SECRET):

1. The admin clicks "Continue with Facebook". A popup runs Facebook's login
   dialog and comes back to the platform's one redirect URI (public domain);
   the signed `state` names the tenant and the admin.
2. The code is exchanged for a long-lived user token, which lists the Pages
   the person manages. Each Page comes with its own Page token, which does not
   expire when derived from a long-lived user token.
3. The admin connects a Page: the app is subscribed to the Page's `leadgen`
   field and the Page is routed to this tenant (tenants.MetaPageRoute).
4. Meta posts each new lead to the platform webhook, which routes it by Page
   id and hands it to `handle_leadgen` in the tenant's schema.
5. A poll every few minutes (`poll_tenant`) fetches anything the webhook
   missed, so a lead never waits for a button press.

Each form chooses who gets its leads: the usual rules, one agent, or a team
in turn.
"""
import json
import logging
import secrets as pysecrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

STATE_SALT = "meta-leads-oauth"
STATE_MAX_AGE = 15 * 60  # seconds the login popup may take

# Lead fields to ask Meta for. The ad/campaign names need ads permissions on
# the ad account; when Meta refuses them the lead is fetched without.
LEAD_FIELDS = (
    "id,created_time,field_data,ad_id,ad_name,adset_id,adset_name,"
    "campaign_id,campaign_name,form_id,platform"
)
LEAD_FIELDS_BASIC = "id,created_time,field_data,form_id,platform"


class MetaError(Exception):
    """A Graph API failure, with a message fit to show an admin."""

    def __init__(self, message: str, code=None):
        super().__init__(message)
        self.message = message
        self.code = code


# ============================================================
# Settings and URLs
# ============================================================

def graph_version() -> str:
    return getattr(settings, "META_GRAPH_API_VERSION", "v25.0")


def graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{graph_version()}/{path.lstrip('/')}"


def is_configured() -> bool:
    """Is the platform Meta app set up? Without it the button is hidden."""
    return bool(settings.META_APP_ID and settings.META_APP_SECRET)


def redirect_uri() -> str:
    return (settings.META_OAUTH_REDIRECT_URI
            or f"https://{settings.BASE_DOMAIN}/api/v1/public/meta/oauth/callback/")


def webhook_url() -> str:
    return f"https://{settings.BASE_DOMAIN}/api/v1/public/meta/leadgen/"


# ============================================================
# Graph helpers
# ============================================================

def _call(method: str, path: str, *, params=None, timeout=20) -> dict:
    url = path if path.startswith("https://") else graph_url(path)
    try:
        resp = requests.request(method, url, params=params, timeout=timeout)
    except requests.RequestException as exc:
        raise MetaError(f"Could not reach Facebook: {exc.__class__.__name__}") from exc
    try:
        data = resp.json()
    except ValueError:
        data = {}
    if resp.status_code >= 400 or (isinstance(data, dict) and data.get("error")):
        err = (data or {}).get("error") or {}
        message = err.get("error_user_msg") or err.get("message") or f"Facebook returned {resp.status_code}"
        raise MetaError(message, code=err.get("code"))
    return data


def _get_all(path: str, params: dict, limit_pages: int = 20) -> list:
    """Follow `paging.next` and return every item in `data`."""
    out = []
    data = _call("GET", path, params=params)
    for _ in range(limit_pages):
        out.extend(data.get("data", []))
        nxt = (data.get("paging") or {}).get("next")
        if not nxt:
            break
        data = _call("GET", nxt)
    return out


# ============================================================
# 1. Login
# ============================================================

def make_state(schema_name: str, agent_id: int) -> str:
    return signing.dumps(
        {"s": schema_name, "a": agent_id, "n": pysecrets.token_urlsafe(6)}, salt=STATE_SALT,
    )


def read_state(state: str) -> dict:
    """The signed state back, or MetaError when forged or too old."""
    try:
        return signing.loads(state or "", salt=STATE_SALT, max_age=STATE_MAX_AGE)
    except signing.SignatureExpired as exc:
        raise MetaError("The Facebook sign-in took too long. Please try again.") from exc
    except signing.BadSignature as exc:
        raise MetaError("This sign-in link is not valid. Please start again from the CRM.") from exc


def login_url(schema_name: str, agent_id: int) -> str:
    params = {
        "client_id": settings.META_APP_ID,
        "redirect_uri": redirect_uri(),
        "state": make_state(schema_name, agent_id),
        "response_type": "code",
    }
    if settings.META_LOGIN_CONFIG_ID:
        params["config_id"] = settings.META_LOGIN_CONFIG_ID
    else:
        params["scope"] = settings.META_LOGIN_SCOPES
    return f"https://www.facebook.com/{graph_version()}/dialog/oauth?{urlencode(params)}"


def exchange_code(code: str) -> tuple[str, int | None]:
    """The login code → a long-lived user token and its lifetime in seconds."""
    short = _call("GET", "oauth/access_token", params={
        "client_id": settings.META_APP_ID,
        "client_secret": settings.META_APP_SECRET,
        "redirect_uri": redirect_uri(),
        "code": code,
    })
    token = short.get("access_token", "")
    if not token:
        raise MetaError("Facebook did not return an access token.")
    try:
        long = _call("GET", "oauth/access_token", params={
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": token,
        })
        return long.get("access_token") or token, long.get("expires_in")
    except MetaError:
        # A Business-login token may already be long-lived.
        return token, short.get("expires_in")


def list_pages(user_token: str) -> list[dict]:
    return _get_all("me/accounts", {
        "access_token": user_token,
        "fields": "id,name,access_token,tasks,picture{url}",
        "limit": 100,
    })


def store_login(code: str, agent_id: int | None) -> dict:
    """
    Finish the login in the CURRENT (tenant) schema: keep the token and list
    the Pages. Pages already connected keep their settings; their token is
    refreshed, which is also how an expired or revoked Page is repaired.
    """
    from apps.integrations.models import MetaConnection, MetaLeadPage

    user_token, expires_in = exchange_code(code)
    me = _call("GET", "me", params={"access_token": user_token, "fields": "id,name"})
    try:
        perms = _call("GET", "me/permissions", params={"access_token": user_token}).get("data", [])
        granted = sorted(p["permission"] for p in perms if p.get("status") == "granted")
    except MetaError:
        granted = []

    MetaConnection.objects.create(
        fb_user_id=str(me.get("id", "")),
        fb_user_name=me.get("name", ""),
        secrets={"user_token": user_token},
        token_expires_at=timezone.now() + timedelta(seconds=int(expires_in)) if expires_in else None,
        granted_scopes=granted,
        connected_by_id=agent_id,
    )

    pages = list_pages(user_token)
    for p in pages:
        page, _ = MetaLeadPage.objects.get_or_create(page_id=str(p["id"]))
        page.name = p.get("name", "")[:200]
        page.picture_url = (((p.get("picture") or {}).get("data") or {}).get("url") or "")[:1000]
        if p.get("access_token"):
            page.secrets = {"page_token": p["access_token"]}
        page.save()

    missing = [s for s in ("leads_retrieval", "pages_manage_metadata", "pages_show_list") if s not in granted]
    return {"pages": len(pages), "name": me.get("name", ""), "missing_permissions": missing if granted else []}


# ============================================================
# 2. Pages and forms
# ============================================================

def _current_tenant():
    from django_tenants.utils import get_tenant_model

    return get_tenant_model().objects.get(schema_name=connection.schema_name)


def route_owner(page_id: str):
    """The tenant this Page's leads go to now, or None."""
    from apps.tenants.models import MetaPageRoute

    route = MetaPageRoute.objects.filter(page_id=page_id).select_related("tenant").first()
    return route.tenant if route else None


def connect_page(page, agent=None):
    """
    Start receiving this Page's leads: route it here, subscribe the app to its
    `leadgen` field and list its forms.
    """
    from apps.core.constants import LeadSource
    from apps.integrations.models import LeadSourceConfig
    from apps.tenants.models import MetaPageRoute

    if not page.token:
        raise MetaError("Facebook did not give access to this Page. Sign in again and tick it.")
    tenant = _current_tenant()
    owner = route_owner(page.page_id)
    if owner is not None and owner.pk != tenant.pk:
        raise MetaError(
            f'"{page.name}" is already connected to another DialSathi workspace. '
            "Disconnect it there first."
        )

    _call("POST", f"{page.page_id}/subscribed_apps", params={
        "subscribed_fields": "leadgen", "access_token": page.token,
    })
    MetaPageRoute.objects.update_or_create(
        page_id=page.page_id, defaults={"tenant": tenant, "page_name": page.name[:200]},
    )

    page.connected = True
    page.connected_at = timezone.now()
    page.connected_by = agent
    page.last_error = ""
    # Start the safety-net poll from now: earlier leads are not imported
    # unless the admin asks (the "Fetch now" button looks back further).
    page.last_polled_at = timezone.now()
    page.save()

    config = LeadSourceConfig.objects.filter(source=LeadSource.META_FACEBOOK).first()
    if config is None:
        LeadSourceConfig.objects.create(
            source=LeadSource.META_FACEBOOK, is_active=True,
            credentials={"mode": "facebook_login"},
            options={"duplicate_action": "skip"},
        )
    elif not config.is_active:
        config.is_active = True
        config.save(update_fields=["is_active", "status"])

    refresh_forms(page, first_time=True)
    return page


def disconnect_page(page):
    """Stop receiving this Page's leads. Its forms and settings are kept."""
    from apps.tenants.models import MetaPageRoute

    if page.token:
        try:
            _call("DELETE", f"{page.page_id}/subscribed_apps", params={"access_token": page.token})
        except MetaError as exc:
            # Already removed in Facebook, or the token is gone: either way
            # nothing more will be routed here once the route is deleted.
            logger.info("[MetaConnect] unsubscribe %s: %s", page.page_id, exc.message)
    MetaPageRoute.objects.filter(page_id=page.page_id, tenant=_current_tenant()).delete()
    page.connected = False
    page.save(update_fields=["connected", "updated_at"])


def refresh_forms(page, *, first_time: bool = False) -> int:
    """
    Bring the Page's form list up to date. A form seen for the first time is
    switched on when the Page takes new forms automatically (and, on the first
    connect, when it is active).
    """
    from apps.integrations.models import MetaLeadForm

    forms = _get_all(f"{page.page_id}/leadgen_forms", {
        "access_token": page.token, "fields": "id,name,status", "limit": 100,
    })
    for f in forms:
        form, created = MetaLeadForm.objects.get_or_create(
            form_id=str(f["id"]),
            defaults={"page": page, "name": (f.get("name") or "")[:300], "status": f.get("status", ""),
                      "enabled": (f.get("status") == "ACTIVE") and (first_time or page.auto_add_new_forms)},
        )
        if not created:
            form.page = page
            form.name = (f.get("name") or "")[:300]
            form.status = f.get("status", "")
            form.save(update_fields=["page", "name", "status", "updated_at"])
    return len(forms)


# ============================================================
# 3. One lead
# ============================================================

def _fetch_lead(leadgen_id: str, token: str) -> dict:
    try:
        return _call("GET", leadgen_id, params={"access_token": token, "fields": LEAD_FIELDS})
    except MetaError:
        # Usually: no ads permission on the ad account for the names.
        return _call("GET", leadgen_id, params={"access_token": token, "fields": LEAD_FIELDS_BASIC})


def build_lead_data(data: dict, mapping: dict, form=None) -> dict:
    """A Graph lead → the dict BaseWebhookView._create_or_update_lead takes."""
    from apps.integrations.field_mapping import apply_field_mapping, flatten_meta_field_data

    raw = flatten_meta_field_data(data.get("field_data", []))
    lead_data, custom = apply_field_mapping(raw, mapping or {})
    lead_data["source_lead_id"] = str(data.get("id", ""))
    lead_data["custom_values"] = custom
    lead_data.setdefault("campaign_name", data.get("campaign_name", "") or "")
    lead_data.setdefault("ad_name", data.get("ad_name") or data.get("adset_name") or "")
    lead_data.setdefault("meta", {})
    lead_data["meta"].update({
        "campaign_id": data.get("campaign_id", ""),
        "campaign_name": data.get("campaign_name", ""),
        "adset_name": data.get("adset_name", ""),
        "ad_id": data.get("ad_id", ""),
        "ad_name": data.get("ad_name", ""),
        "form_id": data.get("form_id", ""),
        "form_name": form.name if form is not None else "",
        "platform": data.get("platform", ""),
        "via": "facebook_login",
    })
    return lead_data


def pick_assignee(form):
    """
    Who this form's next lead goes to, or None for the usual rules.

    A team takes turns in a stable order (by agent id), the cursor kept on the
    form row under a lock so two leads arriving together go to two people.
    """
    from apps.authentication.models import Agent
    from apps.integrations.models import MetaLeadForm

    if form is None:
        return None
    if form.assign_mode == MetaLeadForm.ASSIGN_AGENT:
        agent = form.assign_agent
        return agent if agent is not None and agent.is_active else None
    if form.assign_mode == MetaLeadForm.ASSIGN_TEAM and form.assign_team_id:
        with transaction.atomic():
            locked = MetaLeadForm.objects.select_for_update().get(pk=form.pk)
            members = list(
                Agent.objects.filter(
                    team_memberships__team_id=locked.assign_team_id, is_active=True,
                ).order_by("pk").distinct()
            )
            if not members:
                return None
            nxt = (locked.rr_cursor + 1) % len(members)
            locked.rr_cursor = nxt
            locked.save(update_fields=["rr_cursor"])
            return members[nxt]
    return None


def handle_leadgen(page_id: str, form_id: str, leadgen_id: str, *, lead_json: dict | None = None,
                   via: str = "webhook") -> str:
    """
    Make sure Meta lead `leadgen_id` is in the CRM. Runs in the tenant schema.
    Safe to call twice for the same lead (webhook retry + poll): the Meta lead
    id is checked first, and the phone dedupe catches the rest.

    Returns what happened: created / duplicate / updated / form_off /
    page_not_connected / integration_off / no_phone / quota / error.
    """
    from apps.core.constants import LeadSource
    from apps.core.exceptions import PlanLimitExceededException
    from apps.integrations.models import LeadSourceConfig, MetaLeadForm, MetaLeadPage
    from apps.integrations.views import MetaLeadAdsWebhookView
    from apps.leads.models import Lead

    page = MetaLeadPage.objects.filter(page_id=str(page_id), connected=True).first()
    if page is None:
        return "page_not_connected"
    config = LeadSourceConfig.objects.filter(source=LeadSource.META_FACEBOOK).first()
    if config is not None and not config.is_active:
        return "integration_off"

    form = MetaLeadForm.objects.filter(form_id=str(form_id)).first() if form_id else None
    if form is None and form_id:
        try:
            info = _call("GET", str(form_id), params={"access_token": page.token, "fields": "name,status"})
        except MetaError:
            info = {}
        form = MetaLeadForm.objects.create(
            page=page, form_id=str(form_id), name=(info.get("name") or "")[:300],
            status=info.get("status", ""), enabled=page.auto_add_new_forms,
        )
    if form is not None and not form.enabled:
        return "form_off"

    if Lead.objects.filter(source_lead_id=str(leadgen_id)).exists():
        return "duplicate"

    try:
        data = lead_json or _fetch_lead(str(leadgen_id), page.token)
    except MetaError as exc:
        page.last_error = f"Could not read a lead: {exc.message}"[:500]
        page.save(update_fields=["last_error", "updated_at"])
        raise

    mapping = ((config.options if config else None) or {}).get("field_mapping", {})
    lead_data = build_lead_data(data, mapping, form)
    if not lead_data.get("phone"):
        return "no_phone"

    view = MetaLeadAdsWebhookView()
    view.source = LeadSource.META_INSTAGRAM if data.get("platform") == "ig" else LeadSource.META_FACEBOOK
    dup_action = ((config.options if config else None) or {}).get("duplicate_action", "skip")
    try:
        created, lead = view._create_or_update_lead(
            lead_data, config, duplicate_action=dup_action, assign_to=pick_assignee(form),
        )
    except PlanLimitExceededException:
        page.last_error = "Lead limit of your plan reached — new Facebook leads are waiting."
        page.save(update_fields=["last_error", "updated_at"])
        return "quota"
    except ValueError:
        return "no_phone"

    if not created:
        return "updated" if dup_action == "update" else "duplicate"

    now = timezone.now()
    MetaLeadPage.objects.filter(pk=page.pk).update(
        leads_received=F("leads_received") + 1, last_lead_at=now, last_error="",
    )
    if form is not None:
        MetaLeadForm.objects.filter(pk=form.pk).update(
            leads_received=F("leads_received") + 1, last_lead_at=now,
        )
    if config is not None:
        config.total_leads_received = (config.total_leads_received or 0) + 1
        config.last_received_at = now
        config.error_message = ""
        config.save(update_fields=["total_leads_received", "last_received_at", "error_message"])
    logger.info("[MetaConnect] lead %s from page %s form %s via %s", leadgen_id, page_id, form_id, via)
    return "created"


# ============================================================
# 4. Safety-net poll
# ============================================================

def _form_leads_since(form, token: str, since) -> list[dict]:
    """Leads on a form created after `since` (newest first, bounded)."""
    filtering = json.dumps([{
        "field": "time_created", "operator": "GREATER_THAN", "value": int(since.timestamp()),
    }])
    params = {"access_token": token, "fields": LEAD_FIELDS, "filtering": filtering, "limit": 100}
    try:
        return _get_all(f"{form.form_id}/leads", params, limit_pages=5)
    except MetaError:
        params["fields"] = LEAD_FIELDS_BASIC
        return _get_all(f"{form.form_id}/leads", params, limit_pages=5)


def poll_page(page, *, lookback=None) -> dict:
    """
    Fetch the Page's recent leads and import any the webhook missed.

    Looks back from the last poll with a 15-minute overlap (Meta can be slow
    to make a lead readable); `lookback` overrides, for "Fetch now".
    """
    started = timezone.now()
    since = (started - lookback) if lookback else (
        (page.last_polled_at or started - timedelta(hours=1)) - timedelta(minutes=15)
    )
    counts = {"created": 0, "duplicate": 0, "skipped": 0, "failed": 0}
    try:
        refresh_forms(page)
    except MetaError as exc:
        page.last_error = f"Facebook: {exc.message}"[:500]
        page.save(update_fields=["last_error", "updated_at"])
        counts["failed"] += 1
        return counts

    for form in page.forms.filter(enabled=True):
        try:
            leads = _form_leads_since(form, page.token, since)
        except MetaError as exc:
            page.last_error = f"Form {form.name or form.form_id}: {exc.message}"[:500]
            counts["failed"] += 1
            continue
        for item in leads:
            try:
                result = handle_leadgen(page.page_id, form.form_id, str(item.get("id")),
                                        lead_json=item, via="poll")
            except MetaError:
                counts["failed"] += 1
                continue
            if result == "created":
                counts["created"] += 1
            elif result in ("duplicate", "updated"):
                counts["duplicate"] += 1
            elif result == "quota":
                counts["failed"] += 1
                break
            else:
                counts["skipped"] += 1

    page.last_polled_at = started
    page.save(update_fields=["last_polled_at", "last_error", "updated_at"])
    return counts


def poll_tenant(*, lookback=None) -> dict:
    """Every connected Page in this tenant, plus the older manual set-up."""
    from apps.core.constants import LeadSource
    from apps.integrations.meta_sync import sync_meta_leads
    from apps.integrations.models import LeadSourceConfig, MetaLeadPage

    totals = {"created": 0, "duplicate": 0, "skipped": 0, "failed": 0, "pages": 0}
    config = LeadSourceConfig.objects.filter(source=LeadSource.META_FACEBOOK).first()
    if config is not None and not config.is_active:
        return totals

    pages = list(MetaLeadPage.objects.filter(connected=True))
    for page in pages:
        totals["pages"] += 1
        for k, v in poll_page(page, lookback=lookback).items():
            totals[k] = totals.get(k, 0) + v

    # The manual set-up (a Page token pasted into the integration) was only
    # ever pulled by the "Sync now" button. Pull it here too, unless that
    # Page is now connected through Facebook login.
    creds = (config.credentials or {}) if config else {}
    legacy_page = creds.get("page_id") or ((config.options or {}).get("page_id") if config else None)
    if config is not None and creds.get("access_token") and legacy_page and \
            str(legacy_page) not in {p.page_id for p in pages}:
        result = sync_meta_leads(config, max_per_form=25)
        if not result.get("error"):
            totals["created"] += result.get("created", 0)
            totals["duplicate"] += result.get("skipped", 0)
        else:
            totals["failed"] += 1
    return totals
