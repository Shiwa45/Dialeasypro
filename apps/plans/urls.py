"""
TeleCRM Backend — apps/plans/urls.py
Plan list URL — included from apps/tenants/urls.py
"""
from django.urls import path
from apps.plans.views import PublicPlanListView

urlpatterns = [
    path("plans/", PublicPlanListView.as_view(), name="plan_list"),
]
