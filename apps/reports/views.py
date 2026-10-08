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
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.db.models.functions import TruncDate
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


def _fill_days(daily_rows, date_from, date_to, max_days: int = 400) -> list[dict]:
    """Daily call rows → one entry per calendar day in [date_from, date_to]."""
    from datetime import date as _date

    by_day = {str(r["date"]): r for r in daily_rows}
    try:
        start, end = _date.fromisoformat(str(date_from)), _date.fromisoformat(str(date_to))
    except ValueError:
        start = end = None
    if not start or not end or end < start or (end - start).days > max_days:
        days = sorted(by_day)
    else:
        days = [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]
    out = []
    for d in days:
        row = by_day.get(d, {"total": 0, "connected": 0})
        out.append({
            "date": d,
            "total": row["total"],
            "connected": row["connected"],
            "connection_rate": round(row["connected"] / max(row["total"], 1) * 100, 1),
        })
    return out


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
            # Active agents, plus anyone deactivated since who made calls in
            # the range — their work in that period still happened.
            called = CallLog.objects.filter(
                started_at__date__gte=date_from, started_at__date__lte=date_to, agent__isnull=False,
            ).values("agent_id")
            agents_qs = Agent.objects.filter(Q(is_active=True) | Q(pk__in=called))
            if agent_id:
                agents_qs = agents_qs.filter(pk=agent_id)

            report = []
            for agent in agents_qs:
                owned = Lead.objects.filter(assigned_to=agent, is_deleted=False)
                # Leads the agent RECEIVED in the period: assigned to them in
                # it (or created in it, for leads with no assignment time).
                # Counting only leads created in the period showed "0 leads"
                # for an agent working a hundred older ones.
                leads = owned.filter(
                    Q(assigned_at__date__gte=date_from, assigned_at__date__lte=date_to)
                    | Q(assigned_at__isnull=True, created_at__date__gte=date_from,
                        created_at__date__lte=date_to)
                )
                calls = CallLog.objects.filter(
                    agent=agent,
                    started_at__date__gte=date_from,
                    started_at__date__lte=date_to,
                )
                call_stats = calls.aggregate(
                    total_calls=Count("id"),
                    connected=Count("id", filter=Q(is_connected=True)),
                    total_duration=Sum("duration_seconds", filter=Q(is_connected=True)),
                )
                total = leads.count()
                won = leads.filter(status=LeadStatus.CONVERTED).count()
                report.append({
                    "agent_id": agent.pk,
                    "agent_name": agent.name,
                    "agent_role": agent.role,
                    "leads": {
                        "total": total,
                        "owned": owned.count(),
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

            # By disposition, with its group (connected / not connected). Calls
            # with no outcome are a bucket of their own rather than missing.
            by_disposition = list(
                qs.filter(disposition__isnull=False)
                .order_by()
                .values("disposition_id", "disposition__name", "disposition__is_positive", "disposition__category")
                .annotate(count=Count("id"))
                .order_by("-count")
            )
            no_outcome = qs.filter(disposition__isnull=True).count()
            if no_outcome:
                by_disposition.append({
                    "disposition_id": None, "disposition__name": "No outcome",
                    "disposition__is_positive": False, "disposition__category": None,
                    "count": no_outcome,
                })
            # Answered calls with no talk time: a data-quality flag, not a rate.
            connected_without_duration = qs.filter(is_connected=True, duration_seconds=0).count()

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
                    "connected_without_duration": connected_without_duration,
                    "no_outcome_calls": no_outcome,
                },
                # Every day in the range, zeros included. Days without calls
                # used to be missing, so the chart's axis jumped from 12 Sep
                # to 27 Sep as if they were consecutive.
                "daily_trend": _fill_days(daily, date_from, date_to),
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
        # ?current=1 → where every lead stands NOW, whenever it arrived. The
        # dashboard's pipeline wants that; the dated funnel only counts leads
        # created in the range, so a tenant whose leads all came in five weeks
        # ago saw "No pipeline data yet" on a full pipeline.
        current = params.get("current") in ("1", "true", "yes")
        date_from = params.get("date_from", (timezone.localdate() - timedelta(days=90)).isoformat())
        date_to = params.get("date_to", timezone.localdate().isoformat())

        cache_key = _report_key("funnel", scope_key, "current" if current else date_from, "" if current else date_to)

        def compute():
            qs = Lead.objects.filter(is_deleted=False)
            if not current:
                qs = qs.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
            if is_scoped:
                qs = qs.filter(assigned_to=agent)
            total = qs.count()
            # Follow-up is a pipeline stage too (the same one as Interested);
            # it was missing, so those leads vanished from the funnel.
            funnel_stages = [
                LeadStatus.NEW, LeadStatus.ATTEMPTED, LeadStatus.CONTACTED,
                LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP, LeadStatus.NEGOTIATION,
                LeadStatus.CONVERTED,
            ]
            closed_stages = [LeadStatus.NOT_INTERESTED, LeadStatus.LOST, LeadStatus.INVALID, LeadStatus.DUPLICATE]
            counts = {r["status"]: r["n"] for r in qs.order_by().values("status").annotate(n=Count("id"))}
            labels = dict(LeadStatus.CHOICES)

            def row(stage):
                count = counts.get(stage, 0)
                return {
                    "status": stage,
                    "label": labels.get(stage, stage),
                    "count": count,
                    "pct_of_total": round(count / total * 100, 1) if total else 0,
                }

            funnel = [row(s) for s in funnel_stages]
            closed = [row(s) for s in closed_stages]
            return {
                "funnel": funnel,
                "closed": closed,
                # Every lead, open and closed: the dashboard's pipeline shows
                # all of them (Not Interested used to be left out of the total).
                "pipeline": funnel + closed,
                "total": total,
                "lost": counts.get(LeadStatus.LOST, 0),
            }

        return Response({
            "period": None if current else {"date_from": date_from, "date_to": date_to},
            "current": current,
            **_cached(cache_key, compute),
        })


class AgentOutcomeReportView(APIView):
    """
    GET /api/v1/reports/agent-outcomes/?date_from&date_to

    What each agent's calls came to, outcome by outcome — built from the
    CALLS an agent made, not from the leads they own. Agent Performance reads
    lead ownership, so an agent calling a colleague's leads got no credit for
    any of it, and nothing showed how many calls ended Interested vs Busy.
    """

    permission_classes = [IsAuthenticatedAgent, HasFeatureAccess]
    required_feature = FeatureKey.BASIC_REPORTS

    def get(self, request):
        from apps.calls.models import CallDisposition, CallLog

        agent = request.user
        is_scoped = not sees_everything(agent)
        params = request.query_params
        date_from = params.get("date_from", (timezone.localdate() - timedelta(days=30)).isoformat())
        date_to = params.get("date_to", timezone.localdate().isoformat())
        scope_key = f"agent{agent.pk}" if is_scoped else "all"
        cache_key = _report_key("agent_outcomes", scope_key, date_from, date_to)

        def compute():
            qs = CallLog.objects.filter(
                started_at__date__gte=date_from, started_at__date__lte=date_to, agent__isnull=False,
            )
            if is_scoped:
                qs = qs.filter(agent=agent)

            totals = (
                qs.values("agent_id", "agent__name")
                .annotate(
                    dials=Count("id"),
                    connected=Count("id", filter=Q(is_connected=True)),
                    talk_seconds=Sum("duration_seconds", filter=Q(is_connected=True)),
                    no_outcome=Count("id", filter=Q(disposition__isnull=True)),
                )
                .order_by("agent__name")
            )
            per_outcome = {}
            for row in (
                qs.filter(disposition__isnull=False)
                .order_by()
                .values("agent_id", "disposition_id")
                .annotate(n=Count("id"))
            ):
                per_outcome.setdefault(row["agent_id"], {})[str(row["disposition_id"])] = row["n"]

            used = set(qs.filter(disposition__isnull=False).values_list("disposition_id", flat=True))
            dispositions = [
                {"id": d.pk, "name": d.name, "category": d.category, "is_positive": d.is_positive}
                for d in CallDisposition.objects.filter(Q(is_active=True) | Q(pk__in=used))
                .order_by("category", "sort_order", "name")
            ]

            agents = []
            for row in totals:
                dials = row["dials"] or 0
                connected = row["connected"] or 0
                agents.append({
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent__name"],
                    "dials": dials,
                    "connected": connected,
                    "connection_rate": round(connected / dials * 100, 1) if dials else 0,
                    "talk_seconds": row["talk_seconds"] or 0,
                    "no_outcome": row["no_outcome"] or 0,
                    "outcomes": per_outcome.get(row["agent_id"], {}),
                })
            return {"dispositions": dispositions, "agents": agents}

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
            total_duration=Sum("duration_seconds", filter=Q(is_connected=True)),
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


# ============================================================
# My performance — the agent's own dashboard
# ============================================================

class MyPerformanceView(APIView):
    """
    GET /api/v1/reports/my-performance/?days=1|7|30

    The signed-in person's OWN numbers, and nobody else's.

    This deliberately takes no agent_id parameter, ever. Every other report
    here is "the team, filtered"; this one is "me", and the cleanest way to
    guarantee an agent can never read a colleague's numbers through it is for
    the endpoint to have no way of being asked for them.

    Not plan-gated: an agent's view of their own day is basic to the product,
    not an analytics upsell. The tenant-wide agent-performance report stays
    behind AGENT_PERFORMANCE_REPORTS.
    """

    permission_classes = [IsAuthenticatedAgent]
    ALLOWED_DAYS = (1, 7, 30)

    def get(self, request):
        from datetime import datetime, time as dtime

        from apps.calls.models import CallLog
        from apps.core.constants import CallDirection
        from apps.leads.models import FollowUp, Lead, LeadActivity

        me = request.user
        try:
            days = int(request.query_params.get("days", 7))
        except (TypeError, ValueError):
            days = 7
        if days not in self.ALLOWED_DAYS:
            days = 7

        now = timezone.now()
        today = timezone.localdate()
        date_from = today - timedelta(days=days - 1)
        tz = timezone.get_current_timezone()
        # Local-midnight boundaries, so "today" means the agent's working day
        # in IST, not a UTC day that starts at 5:30 in the morning.
        start = timezone.make_aware(datetime.combine(date_from, dtime.min), tz)
        end_of_today = timezone.make_aware(datetime.combine(today, dtime.max), tz)

        # ---- Calls --------------------------------------------
        calls = CallLog.objects.filter(agent=me, started_at__gte=start, started_at__lte=end_of_today)
        agg = calls.aggregate(
            total=Count("id"),
            connected=Count("id", filter=Q(is_connected=True)),
            talk=Sum("duration_seconds", filter=Q(is_connected=True)),
            outbound=Count("id", filter=Q(direction=CallDirection.OUTBOUND)),
            inbound=Count("id", filter=Q(direction=CallDirection.INBOUND)),
            missed=Count("id", filter=Q(direction=CallDirection.MISSED)),
        )
        total_calls = agg["total"] or 0
        connected = agg["connected"] or 0
        talk = agg["talk"] or 0

        # One row per day, zero-filled — a chart with gaps on the days nothing
        # happened reads as missing data rather than as a quiet day.
        per_day = {
            row["day"]: row
            for row in calls.annotate(day=TruncDate("started_at"))
            .values("day")
            .annotate(
                total=Count("id"),
                connected=Count("id", filter=Q(is_connected=True)),
                talk=Sum("duration_seconds", filter=Q(is_connected=True)),
            )
        }
        by_day = []
        for i in range(days):
            d = date_from + timedelta(days=i)
            row = per_day.get(d, {})
            by_day.append({
                "date": d.isoformat(),
                "calls": row.get("total") or 0,
                "connected": row.get("connected") or 0,
                "talk_seconds": row.get("talk") or 0,
            })

        today_calls = CallLog.objects.filter(agent=me, started_at__date=today)
        first_last = today_calls.aggregate(first=Min("started_at"), last=Max("started_at"))

        # ---- Leads --------------------------------------------
        my_leads = Lead.objects.filter(assigned_to=me, is_deleted=False)
        by_status = dict(
            my_leads.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )
        assigned_total = sum(by_status.values())
        converted_total = by_status.get(LeadStatus.CONVERTED, 0)

        # Conversions *this agent* made in the period, read from the activity
        # trail — Lead carries no converted_at, and counting leads currently
        # in "converted" would credit this period with last month's wins.
        converted_in_period = (
            LeadActivity.objects.filter(
                performed_by=me,
                activity_type="status_change",
                meta__new_status=LeadStatus.CONVERTED,
                timestamp__gte=start,
            )
            .values("lead_id").distinct().count()
        )
        new_in_period = my_leads.filter(assigned_at__gte=start).count()

        # ---- Follow-ups ---------------------------------------
        open_fu = FollowUp.objects.filter(assigned_to=me, is_completed=False)
        next_followups = [
            {
                "id": f.pk,
                "lead_id": f.lead_id,
                "lead_name": f.lead.name,
                "scheduled_at": f.scheduled_at.isoformat(),
                "type": f.followup_type,
                "overdue": f.scheduled_at < now,
            }
            for f in open_fu.filter(lead__is_deleted=False)
            .select_related("lead").order_by("scheduled_at")[:8]
        ]

        return Response({
            "period": {
                "days": days,
                "date_from": date_from.isoformat(),
                "date_to": today.isoformat(),
            },
            "calls": {
                "total": total_calls,
                "connected": connected,
                "connection_rate": round(connected / total_calls * 100, 1) if total_calls else 0,
                "talk_seconds": talk,
                "avg_talk_seconds": round(talk / connected) if connected else 0,
                "outbound": agg["outbound"] or 0,
                "inbound": agg["inbound"] or 0,
                "missed": agg["missed"] or 0,
            },
            "calls_by_day": by_day,
            "today": {
                "calls": today_calls.count(),
                "first_call_at": first_last["first"].isoformat() if first_last["first"] else None,
                "last_call_at": first_last["last"].isoformat() if first_last["last"] else None,
            },
            "leads": {
                "assigned_total": assigned_total,
                "by_status": by_status,
                "new_in_period": new_in_period,
                "converted_in_period": converted_in_period,
                "converted_total": converted_total,
                "conversion_rate": (
                    round(converted_total / assigned_total * 100, 1) if assigned_total else 0
                ),
            },
            "followups": {
                "overdue": open_fu.filter(scheduled_at__lt=now).count(),
                "due_today": open_fu.filter(scheduled_at__gte=now, scheduled_at__lte=end_of_today).count(),
                "upcoming_7d": open_fu.filter(
                    scheduled_at__gt=end_of_today,
                    scheduled_at__lte=end_of_today + timedelta(days=7),
                ).count(),
                "completed_in_period": FollowUp.objects.filter(
                    assigned_to=me, is_completed=True, completed_at__gte=start,
                ).count(),
                "next": next_followups,
            },
        })
