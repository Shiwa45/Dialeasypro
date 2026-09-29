"""
TeleCRM Backend — apps/reports/views.py

Analytics and reporting API views.
All reports are computed on-demand with smart caching (Redis, 5–60 min TTL).

AgentPerformanceReportView  GET /api/v1/reports/agent-performance/
LeadSourceReportView        GET /api/v1/reports/lead-sources/
CallAnalyticsReportView     GET /api/v1/reports/call-analytics/
ConversionFunnelView        GET /api/v1/reports/conversion-funnel/
DailyActivityView           GET /api/v1/reports/daily-activity/
"""
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import (
    HasFeatureAccess,
    IsAuthenticatedAgent,
    IsManagerOrAdmin,
)
from apps.calls.scoping import sees_everything
from apps.core.renderers import CSVRenderer
from apps.core.constants import AgentRole, FeatureKey, LeadStatus, LeadSource

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes


def _report_key(kind: str, *parts) -> str:
    """
    A report cache key that belongs to ONE tenant.

    The keys used to be `report:{kind}:{from}:{to}...` with nothing naming the
    tenant, on a cache whose prefix is the same for everyone. Whichever tenant
    computed a report first had it served to every other tenant asking for the
    same dates within five minutes — agent names and performance, lead
    sources, call analytics and funnel. Every other key in the codebase
    already carries the schema; these four did not.
    """
    from django.db import connection

    return ":".join(["report", connection.schema_name, kind, *[str(p) for p in parts]])


def _cached(key: str, compute_fn, ttl: int = CACHE_TTL):
    """Simple cache helper — compute_fn() result cached at key."""
    result = cache.get(key)
    if result is None:
        result = compute_fn()
        cache.set(key, result, timeout=ttl)
    return result


class AgentPerformanceReportView(APIView):
    """
    GET /api/v1/reports/agent-performance/
    Per-agent performance breakdown: calls, leads, conversions, avg score.

    Params: date_from, date_to, agent_id (optional filter)
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.AGENT_PERFORMANCE_REPORTS

    def get(self, request):
        from apps.calls.models import CallLog
        from apps.leads.models import Lead
        from apps.authentication.models import Agent

        params = request.query_params
        date_from = params.get("date_from", (timezone.localdate() - timedelta(days=30)).isoformat())
        date_to = params.get("date_to", timezone.localdate().isoformat())
        agent_id = params.get("agent_id")

        cache_key = _report_key("agent_perf", date_from, date_to, agent_id or "all")

        def compute():
            agents_qs = Agent.objects.filter(is_active=True)
            if agent_id:
                agents_qs = agents_qs.filter(pk=agent_id)

            report = []
            for agent in agents_qs:
                leads = Lead.objects.filter(
                    assigned_to=agent,
                    created_at__date__gte=date_from,
                    created_at__date__lte=date_to,
                    is_deleted=False,
                )
                calls = CallLog.objects.filter(
                    agent=agent,
                    started_at__date__gte=date_from,
                    started_at__date__lte=date_to,
                )
                call_stats = calls.aggregate(
                    total_calls=Count("id"),
                    connected=Count("id", filter=Q(is_connected=True)),
                    total_duration=Sum("duration_seconds"),
                )
                total = leads.count()
                won = leads.filter(status=LeadStatus.CONVERTED).count()
                report.append({
                    "agent_id": agent.pk,
                    "agent_name": agent.name,
                    "agent_role": agent.role,
                    "leads": {
                        "total": total,
                        "new": leads.filter(status=LeadStatus.NEW).count(),
                        "interested": leads.filter(status=LeadStatus.INTERESTED).count(),
                        "converted": won,
                        "lost": leads.filter(status=LeadStatus.LOST).count(),
                        "conversion_rate": round(won / total * 100, 1) if total else 0,
                        "avg_score": leads.aggregate(a=Avg("score"))["a"] or 0,
                    },
                    "calls": {
                        "total": call_stats["total_calls"] or 0,
                        "connected": call_stats["connected"] or 0,
                        "connection_rate": round(
                            (call_stats["connected"] or 0) / max(call_stats["total_calls"] or 1, 1) * 100, 1
                        ),
                        "total_duration_seconds": call_stats["total_duration"] or 0,
                    },
                })
            return sorted(report, key=lambda x: x["leads"]["converted"], reverse=True)

        return Response({
            "period": {"date_from": date_from, "date_to": date_to},
            "agents": _cached(cache_key, compute),
        })


class LeadSourceReportView(APIView):
    """
    GET /api/v1/reports/lead-sources/
    Lead volume and conversion by source. Identifies best-performing channels.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.ADVANCED_REPORTS

    def get(self, request):
        from apps.leads.models import Lead

        params = request.query_params
        date_from = params.get("date_from", (timezone.localdate() - timedelta(days=30)).isoformat())
        date_to = params.get("date_to", timezone.localdate().isoformat())

        cache_key = _report_key("lead_sources", date_from, date_to)

        def compute():
            qs = Lead.objects.filter(
                created_at__date__gte=date_from,
                created_at__date__lte=date_to,
                is_deleted=False,
            )
            by_source = (
                qs.values("source")
                .annotate(
                    total=Count("id"),
                    converted=Count("id", filter=Q(status=LeadStatus.CONVERTED)),
                    lost=Count("id", filter=Q(status=LeadStatus.LOST)),
                    avg_score=Avg("score"),
                    total_deal_value=Sum("deal_value"),
                )
                .order_by("-total")
            )
            result = []
            for row in by_source:
                total = row["total"]
                conv = row["converted"]
                result.append({
                    "source": row["source"],
                    "source_display": dict(LeadSource.CHOICES).get(row["source"], row["source"]),
                    "total": total,
                    "converted": conv,
                    "lost": row["lost"],
                    "conversion_rate": round(conv / total * 100, 1) if total else 0,
                    "avg_score": round(row["avg_score"] or 0, 1),
                    "total_deal_value": float(row["total_deal_value"] or 0),
                })
            return result

        return Response({
            "period": {"date_from": date_from, "date_to": date_to},
            "by_source": _cached(cache_key, compute),
        })


class CallAnalyticsReportView(APIView):
    """
    GET /api/v1/reports/call-analytics/
    Call volume trends, connection rates, duration distribution, and disposition breakdown.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.BASIC_REPORTS

    def get(self, request):
        from apps.calls.models import CallLog

        agent = request.user
        # Tenant-wide for admins and managers; everyone else sees their own.
        # This used to restrict only the "agent" role, so HR, Accounts and
        # Read-only users got the whole tenant's call analytics.
        is_scoped = not sees_everything(agent)
        scope_key = f"agent{agent.pk}" if is_scoped else "all"

        params = request.query_params
        date_from = params.get("date_from", (timezone.localdate() - timedelta(days=30)).isoformat())
        date_to = params.get("date_to", timezone.localdate().isoformat())

        cache_key = _report_key("call_analytics", scope_key, date_from, date_to)

        def compute():
            qs = CallLog.objects.filter(
                started_at__date__gte=date_from,
                started_at__date__lte=date_to,
            )
            if is_scoped:
                qs = qs.filter(agent=agent)
            aggregate = qs.aggregate(
                total=Count("id"),
                connected=Count("id", filter=Q(is_connected=True)),
                total_duration=Sum("duration_seconds", filter=Q(is_connected=True)),
                avg_duration=Avg("duration_seconds", filter=Q(is_connected=True)),
                total_cost_paise=Sum("call_cost_paise"),
            )

            # Daily trend (last 30 days)
            from django.db.models.functions import TruncDate
            daily = (
                qs.annotate(date=TruncDate("started_at"))
                .values("date")
                .annotate(
                    total=Count("id"),
                    connected=Count("id", filter=Q(is_connected=True)),
                )
                .order_by("date")
            )

            # By disposition
            by_disposition = list(
                qs.filter(disposition__isnull=False)
                .values("disposition__name", "disposition__is_positive")
                .annotate(count=Count("id"))
                .order_by("-count")
            )

            return {
                "summary": {
                    "total_calls": aggregate["total"] or 0,
                    "connected_calls": aggregate["connected"] or 0,
                    "connection_rate": round(
                        (aggregate["connected"] or 0) / max(aggregate["total"] or 1, 1) * 100, 1
                    ),
                    "total_duration_seconds": aggregate["total_duration"] or 0,
                    "avg_duration_seconds": round(aggregate["avg_duration"] or 0),
                    "total_cost_rupees": (aggregate["total_cost_paise"] or 0) / 100,
                },
                "daily_trend": [
                    {
                        "date": str(row["date"]),
                        "total": row["total"],
                        "connected": row["connected"],
                        "connection_rate": round(row["connected"] / max(row["total"], 1) * 100, 1),
                    }
                    for row in daily
                ],
                "by_disposition": by_disposition,
            }

        return Response({
            "period": {"date_from": date_from, "date_to": date_to},
            **_cached(cache_key, compute),
        })


class ConversionFunnelView(APIView):
    """
    GET /api/v1/reports/conversion-funnel/
    Lead pipeline funnel: how many leads at each status stage.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.BASIC_REPORTS

    def get(self, request):
        from apps.leads.models import Lead

        agent = request.user
        # Tenant-wide for admins and managers; everyone else sees their own.
        is_scoped = not sees_everything(agent)
        scope_key = f"agent{agent.pk}" if is_scoped else "all"

        params = request.query_params
        date_from = params.get("date_from", (timezone.localdate() - timedelta(days=90)).isoformat())
        date_to = params.get("date_to", timezone.localdate().isoformat())

        cache_key = _report_key("funnel", scope_key, date_from, date_to)

        def compute():
            qs = Lead.objects.filter(
                created_at__date__gte=date_from,
                created_at__date__lte=date_to,
                is_deleted=False,
            )
            if is_scoped:
                qs = qs.filter(assigned_to=agent)
            total = qs.count()
            funnel_stages = [
                LeadStatus.NEW, LeadStatus.ATTEMPTED, LeadStatus.CONTACTED,
                LeadStatus.INTERESTED, LeadStatus.NEGOTIATION, LeadStatus.CONVERTED,
            ]
            funnel = []
            for stage in funnel_stages:
                count = qs.filter(status=stage).count()
                funnel.append({
                    "status": stage,
                    "label": dict(LeadStatus.CHOICES).get(stage, stage),
                    "count": count,
                    "pct_of_total": round(count / total * 100, 1) if total else 0,
                })
            lost = qs.filter(status=LeadStatus.LOST).count()
            return {"funnel": funnel, "total": total, "lost": lost}

        return Response({
            "period": {"date_from": date_from, "date_to": date_to},
            **_cached(cache_key, compute),
        })


class DailyActivityView(APIView):
    """
    GET /api/v1/reports/daily-activity/
    Today's activity summary: new leads, calls, follow-ups, messages.
    Used for the real-time dashboard ticker.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.BASIC_REPORTS

    def get(self, request):
        from apps.leads.models import Lead, FollowUp
        from apps.calls.models import CallLog

        agent = request.user
        today = timezone.localdate()

        lead_qs = Lead.objects.filter(created_at__date=today, is_deleted=False)
        call_qs = CallLog.objects.filter(started_at__date=today)
        fu_qs = FollowUp.objects.filter(scheduled_at__date=today)

        if not sees_everything(agent):
            lead_qs = lead_qs.filter(assigned_to=agent)
            call_qs = call_qs.filter(agent=agent)
            fu_qs = fu_qs.filter(assigned_to=agent)

        call_stats = call_qs.aggregate(
            total=Count("id"),
            connected=Count("id", filter=Q(is_connected=True)),
            total_duration=Sum("duration_seconds"),
        )

        return Response({
            "date": str(today),
            "leads": {
                "new_today": lead_qs.count(),
                "overdue_followups": Lead.objects.filter(
                    next_followup_at__lt=timezone.now(),
                    next_followup_at__isnull=False,
                    is_deleted=False,
                    **({} if sees_everything(agent) else {"assigned_to": agent}),
                ).count(),
            },
            "calls": {
                "total": call_stats["total"] or 0,
                "connected": call_stats["connected"] or 0,
                "total_duration_seconds": call_stats["total_duration"] or 0,
            },
            "followups": {
                "due_today": fu_qs.count(),
                "completed_today": fu_qs.filter(
                    is_completed=True, completed_at__date=today
                ).count(),
            },
        })


class AgentLoginReportView(APIView):
    """
    GET /api/v1/reports/agent-login/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    GET ...&format=csv  → the same rows as a spreadsheet.

    Every agent's day: first online, last seen, logged-in time and how it
    split between idle, calls, wrap-up and breaks. Defaults to today, which
    is live. Up to 31 days at a time. See apps/reports/login_report.py.
    """

    permission_classes = [IsManagerOrAdmin, HasFeatureAccess]
    required_feature = FeatureKey.AGENT_MONITORING
    # So `?format=csv` (and Accept: text/csv) is not refused before get() runs.
    renderer_classes = [JSONRenderer, CSVRenderer]

    def get(self, request):
        from datetime import date

        from apps.reports.login_report import COLUMNS, MAX_DAYS, build_login_report, csv_cell

        today = timezone.localdate()
        try:
            date_from = date.fromisoformat(request.query_params.get("date_from") or today.isoformat())
            date_to = date.fromisoformat(request.query_params.get("date_to") or date_from.isoformat())
        except ValueError:
            return Response({"error": "invalid_date", "message": "Use YYYY-MM-DD."}, status=400)
        if date_to < date_from:
            date_from, date_to = date_to, date_from
        if date_to > today:
            date_to = today
        if (date_to - date_from).days + 1 > MAX_DAYS:
            return Response(
                {"error": "range_too_long", "message": f"Pick at most {MAX_DAYS} days."}, status=400,
            )

        rows = build_login_report(date_from, date_to)

        if request.query_params.get("format") == "csv" or                 "text/csv" in request.headers.get("Accept", ""):
            from django.http import StreamingHttpResponse

            from apps.core.csv_export import csv_stream

            response = StreamingHttpResponse(
                csv_stream(
                    [label for _, label in COLUMNS],
                    ([csv_cell(key, row[key]) for key, _ in COLUMNS] for row in rows),
                ),
                content_type="text/csv; charset=utf-8",
            )
            response["Content-Disposition"] = (
                f'attachment; filename="agent_login_{date_from}_{date_to}.csv"'
            )
            return response

        return Response({
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "generated_at": timezone.now().isoformat(),
            "rows": rows,
        })
