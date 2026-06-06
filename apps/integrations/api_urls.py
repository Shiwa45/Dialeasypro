"""TeleCRM Backend — apps/integrations/api_urls.py"""
from django.urls import path
from apps.integrations.views import (
    IndiaMArtWebhookView, MetaLeadAdsWebhookView,
    GoogleAdsWebhookView, GenericWebhookView,
    IntegrationConfigListView, IntegrationConfigDetailView,
    WebhookLogListView, MetaFormFieldsView,
)

urlpatterns = [
    # Lead source webhooks (per-tenant, no auth — validated by signature/token)
    path("indiamart/", IndiaMArtWebhookView.as_view(), name="api_indiamart_webhook"),
    path("meta/forms/", MetaFormFieldsView.as_view(), name="api_meta_forms"),
    path("meta/", MetaLeadAdsWebhookView.as_view(), name="api_meta_webhook"),
    path("google/", GoogleAdsWebhookView.as_view(), name="api_google_webhook"),
    path("webhook/<str:token>/", GenericWebhookView.as_view(), name="api_generic_webhook"),

    # Integration management (authenticated)
    path("configs/", IntegrationConfigListView.as_view(), name="api_integration_configs"),
    path("configs/<int:pk>/", IntegrationConfigDetailView.as_view(), name="api_integration_config_detail"),
    path("logs/", WebhookLogListView.as_view(), name="api_webhook_logs"),
]
