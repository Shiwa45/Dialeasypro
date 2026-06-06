"""TeleCRM Backend — apps/plans/views.py"""
from rest_framework import generics
from rest_framework.permissions import AllowAny
from apps.plans.models import Plan
from apps.plans.serializers import PlanSerializer


class PublicPlanListView(generics.ListAPIView):
    """Public API: list all active public plans (no auth required). Used on pricing page."""
    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    queryset = Plan.objects.filter(is_active=True, is_public=True).prefetch_related("features")
