"""
TeleCRM Backend — apps/integrations/meta_connect_views.py

HTTP side of "Continue with Facebook" for Meta Lead Ads (logic in
meta_connect.py).

Tenant API (admins), under /api/v1/integrations/meta/connect/:
  GET    connect/                       status: Pages, forms, who signed in
  POST   connect/start/                 → {url} for the Facebook login popup
  POST   connect/fetch/                 import recent leads now (all Pages)
  POST   connect/pages/<page_id>/connect/
  POST   connect/pages/<page_id>/disconnect/
  POST   connect/pages/<page_id>/refresh-forms/
  PATCH  connect/pages/<page_id>/       {auto_add_new_forms}
  PATCH  connect/forms/<form_id>/       {enabled, assign_mode, assign_agent, assign_team}

Public domain (no tenant in the host):
  GET      /api/v1/public/meta/oauth/callback/   Facebook sends the admin back here
  GET/POST /api/v1/public/meta/leadgen/          the platform app's leadgen webhook
"""
import hashlib
import hmac
import json
import logging
from datetime import timedelta
from html import escape

from django.conf import settings
from django.db import connection
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsTenantAdmin
from apps.core.constants import LeadSource
from apps.integrations import meta_connect
from apps.integrations.meta_connect import MetaError

logger = logging.getLogger(__name__)


# ============================================================
# Tenant API
# ============================================================

def _form_json(form) -> dict:
    return {
        "form_id": form.form_id,
        "name": form.name,
        "status": form.status,
        "enabled": form.enabled,
        "assign_mode": form.assign_mode,
        "assign_agent": form.assign_agent_id,
        "assign_agent_name": form.assign_agent.name if form.assign_agent_id else None,
        "assign_team": form.assign_team_id,
        "assign_team_name": form.assign_team.name if form.assign_team_id else None,
        "leads_received": form.leads_received,
        "last_lead_at": form.last_lead_at,
    }


def _page_json(page) -> dict:
    owner = meta_connect.route_owner(page.page_id)
    elsewhere = owner is not None and owner.schema_name != connection.schema_name
    return {
        "page_id": page.page_id,
        "name": page.name,
        "picture_url": page.picture_url,
        "connected": page.connected,
        "connected_elsewhere": elsewhere,
        "has_token": bool(page.token),
        "auto_add_new_forms": page.auto_add_new_forms,
        "leads_received": page.leads_received,
        "last_lead_at": page.last_lead_at,
        "last_polled_at": page.last_polled_at,
        "last_error": page.last_error,
        "forms": [
            _form_json(f) for f in page.forms.select_related("assign_agent", "assign_team")
            .order_by("-enabled", "name")
        ] if page.connected else [],
    }


def _page_or_404(page_id):
    from apps.integrations.models import MetaLeadPage

    return MetaLeadPage.objects.filter(page_id=str(page_id)).first()


def _meta_error(exc: MetaError):
    return Response({"error": "meta_error", "message": exc.message}, status=status.HTTP_502_BAD_GATEWAY)


class MetaConnectStatusView(APIView):
    """GET /api/v1/integrations/meta/connect/"""

    permission_classes = [IsTenantAdmin]

    def get(self, request):
        from apps.integrations.models import LeadSourceConfig, MetaConnection, MetaLeadPage

        login = MetaConnection.latest()
        config = LeadSourceConfig.objects.filter(source=LeadSource.META_FACEBOOK).first()
        pages = MetaLeadPage.objects.order_by("-connected", "name")
        return Response({
            "available": meta_connect.is_configured(),
            "signed_in": login is not None,
            "signed_in_as": login.fb_user_name if login else "",
            "signed_in_at": login.created_at if login else None,
            "missing_permissions": [
                p for p in ("leads_retrieval", "pages_manage_metadata", "pages_show_list")
                if login and login.granted_scopes and p not in login.granted_scopes
            ],
            "integration_active": bool(config and config.is_active),
            "pages": [_page_json(p) for p in pages],
        })


class MetaConnectStartView(APIView):
    """POST /api/v1/integrations/meta/connect/start/ → {url}"""

    permission_classes = [IsTenantAdmin]

    def post(self, request):
        from apps.integrations.models import LeadSourceConfig
        from apps.integrations.views import check_may_activate

        if not meta_connect.is_configured():
            return Response(
                {"error": "not_available",
                 "message": "Facebook sign-in is not set up on this server yet. Use the manual set-up below."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        config = LeadSourceConfig.objects.filter(source=LeadSource.META_FACEBOOK).first()
        # Plan gate: the Meta source must be in the plan; the cap on how many
        # integrations are active counts only when this adds a new one.
        check_may_activate(
            request, LeadSource.META_FACEBOOK,
            exclude_pk=config.pk if config else None,
            enforce_cap=config is None or not config.is_active,
        )
        return Response({"url": meta_connect.login_url(connection.schema_name, request.user.pk)})


class MetaConnectPageActionView(APIView):
    """POST /api/v1/integrations/meta/connect/pages/<page_id>/<action>/"""

    permission_classes = [IsTenantAdmin]

    def post(self, request, page_id, action):
        page = _page_or_404(page_id)
        if page is None:
            return Response({"error": "not_found", "message": "Sign in with Facebook again to list this Page."},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            if action == "connect":
                meta_connect.connect_page(page, agent=request.user)
            elif action == "disconnect":
                meta_connect.disconnect_page(page)
            elif action == "refresh-forms":
                if not page.connected:
                    return Response({"error": "not_connected", "message": "Connect the Page first."},
                                    status=status.HTTP_400_BAD_REQUEST)
                meta_connect.refresh_forms(page)
            else:
                return Response(status=status.HTTP_404_NOT_FOUND)
        except MetaError as exc:
            page.last_error = exc.message[:500]
            page.save(update_fields=["last_error", "updated_at"])
            return _meta_error(exc)
        page.refresh_from_db()
        return Response(_page_json(page))


class MetaConnectPageView(APIView):
    """PATCH /api/v1/integrations/meta/connect/pages/<page_id>/  {auto_add_new_forms}"""

    permission_classes = [IsTenantAdmin]

    def patch(self, request, page_id):
        page = _page_or_404(page_id)
        if page is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if "auto_add_new_forms" in request.data:
            page.auto_add_new_forms = bool(request.data["auto_add_new_forms"])
            page.save(update_fields=["auto_add_new_forms", "updated_at"])
        return Response(_page_json(page))


class MetaConnectFormView(APIView):
    """PATCH /api/v1/integrations/meta/connect/forms/<form_id>/"""

    permission_classes = [IsTenantAdmin]

    def patch(self, request, form_id):
        from apps.authentication.models import Agent, Team
        from apps.integrations.models import MetaLeadForm

        form = MetaLeadForm.objects.filter(form_id=str(form_id)).first()
        if form is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        data = request.data
        if "enabled" in data:
            form.enabled = bool(data["enabled"])
        if "assign_mode" in data:
            mode = data["assign_mode"]
            if mode not in dict(MetaLeadForm.ASSIGN_CHOICES):
                return Response({"error": "validation_error", "message": "Unknown assignment choice."},
                                status=status.HTTP_400_BAD_REQUEST)
            form.assign_mode = mode
        if "assign_agent" in data:
            agent_id = data["assign_agent"]
            form.assign_agent = Agent.objects.filter(pk=agent_id, is_active=True).first() if agent_id else None
        if "assign_team" in data:
            team_id = data["assign_team"]
            form.assign_team = Team.objects.filter(pk=team_id, is_active=True).first() if team_id else None
            form.rr_cursor = -1
        if form.assign_mode == MetaLeadForm.ASSIGN_AGENT and form.assign_agent is None:
            return Response({"error": "validation_error", "message": "Pick the agent who gets this form's leads."},
                            status=status.HTTP_400_BAD_REQUEST)
        if form.assign_mode == MetaLeadForm.ASSIGN_TEAM and form.assign_team is None:
            return Response({"error": "validation_error", "message": "Pick the team that shares this form's leads."},
                            status=status.HTTP_400_BAD_REQUEST)
        form.save()
        form.refresh_from_db()
        return Response(_form_json(form))


class MetaConnectFetchView(APIView):
    """
    POST /api/v1/integrations/meta/connect/fetch/  {days?: 1..90}

    Import recent leads now — every connected Page, and the older manual set-up.
    Leads already in the CRM are skipped.
    """

    permission_classes = [IsTenantAdmin]

    def post(self, request):
        try:
            days = max(1, min(int(request.data.get("days") or 2), 90))
        except (TypeError, ValueError):
            days = 2
        totals = meta_connect.poll_tenant(lookback=timedelta(days=days))
        msg = f"{totals['created']} new lead(s) imported"
        if totals["duplicate"]:
            msg += f", {totals['duplicate']} already in the CRM"
        if totals["failed"]:
            msg += f". {totals['failed']} problem(s) — see the Page for details"
        return Response({**totals, "message": msg + "."})


# ============================================================
# Public domain: login callback and the platform webhook
# ============================================================

_CALLBACK_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f7f5;color:#1d2420;
display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0}}
.card{{background:#fff;border:1px solid #dfe3dd;border-radius:14px;padding:28px 32px;max-width:420px;text-align:center}}
h1{{font-size:18px;margin:0 0 8px}}p{{margin:0;color:#5b655f;font-size:14px;line-height:1.5}}</style></head>
<body><div class="card"><h1>{title}</h1><p>{body}</p></div>
<script>try{{if(window.opener){{window.opener.postMessage({payload},"*");setTimeout(function(){{window.close()}},{delay});}}}}catch(e){{}}</script>
</body></html>"""


def _callback_page(ok: bool, title: str, body: str, extra: dict | None = None) -> HttpResponse:
    # Nothing secret goes into the message: the opener re-reads the Pages
    # from its own authenticated API.
    payload = json.dumps({"source": "dialsathi-meta", "ok": ok, **(extra or {})})
    html = _CALLBACK_PAGE.format(
        title=escape(title), body=escape(body), payload=payload, delay=800 if ok else 4000,
    )
    return HttpResponse(html, content_type="text/html; charset=utf-8")


class MetaOAuthCallbackView(View):
    """GET /api/v1/public/meta/oauth/callback/?code=…&state=…"""

    def get(self, request):
        from django_tenants.utils import schema_context

        if request.GET.get("error"):
            reason = request.GET.get("error_description") or request.GET.get("error_reason") or "cancelled"
            return _callback_page(False, "Facebook sign-in was cancelled",
                                  "Nothing was connected. You can close this window and try again.",
                                  {"error": reason[:200]})
        try:
            state = meta_connect.read_state(request.GET.get("state", ""))
        except MetaError as exc:
            return _callback_page(False, "Could not finish the sign-in", exc.message, {"error": exc.message})
        schema = state.get("s")
        if not schema or schema == "public":
            return _callback_page(False, "Could not finish the sign-in", "Unknown workspace.")

        try:
            with schema_context(schema):
                result = meta_connect.store_login(request.GET.get("code", ""), state.get("a"))
        except MetaError as exc:
            logger.warning("[MetaConnect] login for %s failed: %s", schema, exc.message)
            return _callback_page(False, "Could not finish the sign-in", exc.message, {"error": exc.message})
        except Exception:  # noqa: BLE001 — show something, log the rest
            logger.exception("[MetaConnect] login for %s crashed", schema)
            return _callback_page(False, "Could not finish the sign-in",
                                  "Something went wrong on our side. Please try again.")

        n = result["pages"]
        body = (f"Found {n} Facebook Page{'s' if n != 1 else ''}. You can close this window."
                if n else "No Pages were shared. Sign in again and tick the Pages you want to connect.")
        return _callback_page(True, "Facebook connected", body,
                              {"pages": n, "missing_permissions": result.get("missing_permissions", [])})


@method_decorator(csrf_exempt, name="dispatch")
class MetaPlatformLeadgenWebhookView(View):
    """
    GET/POST /api/v1/public/meta/leadgen/

    The one webhook of the platform's Meta app (object: page, field: leadgen).
    Verifies Meta's signature with the platform app secret, finds each lead's
    tenant from its Page id, and queues the work. Answers 200 quickly; Meta
    retries anything slow or failed, and the poll catches what is still missed.
    """

    def get(self, request):
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token") or ""
        expected = settings.META_VERIFY_TOKEN or ""
        if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
            return HttpResponse(request.GET.get("hub.challenge", ""), content_type="text/plain")
        return HttpResponse("Forbidden", status=403)

    def post(self, request):
        from apps.integrations.tasks import process_meta_leadgen
        from apps.tenants.models import MetaPageRoute

        secret = settings.META_APP_SECRET or ""
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not secret or not hmac.compare_digest(expected, signature):
            logger.warning("[MetaConnect] leadgen webhook with a bad or missing signature refused")
            return HttpResponse("Unauthenticated webhook", status=401)

        try:
            payload = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return HttpResponse("Bad JSON", status=400)

        queued = unrouted = 0
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                if change.get("field") != "leadgen":
                    continue
                value = change.get("value") or {}
                page_id = str(value.get("page_id") or entry.get("id") or "")
                leadgen_id = str(value.get("leadgen_id") or "")
                if not page_id or not leadgen_id:
                    continue
                route = MetaPageRoute.objects.filter(page_id=page_id).select_related("tenant").first()
                if route is None:
                    unrouted += 1
                    logger.info("[MetaConnect] lead %s for unrouted page %s ignored", leadgen_id, page_id)
                    continue
                process_meta_leadgen.apply_async(
                    args=[route.tenant.schema_name, page_id, str(value.get("form_id") or ""), leadgen_id],
                    queue="integrations",
                )
                queued += 1
        logger.info("[MetaConnect] leadgen webhook: queued=%s unrouted=%s", queued, unrouted)
        return HttpResponse("OK")
