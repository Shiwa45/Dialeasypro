"""TeleCRM Backend — apps/integrations/api_urls.py"""
from django.urls import path
from apps.integrations.views import (
    IndiaMArtWebhookView, MetaLeadAdsWebhookView, MetaWhatsAppWebhookView,
    GoogleAdsWebhookView, GenericWebhookView,
    IntegrationConfigListView, IntegrationConfigDetailView,
    WebhookLogListView, MetaFormFieldsView, MetaSyncLeadsView,
)
from apps.integrations.meta_connect_views import (
    MetaConnectFetchView, MetaConnectFormView, MetaConnectPageActionView,
    MetaConnectPageView, MetaConnectStartView, MetaConnectStatusView,
)

urlpatterns = [
    # Lead source webhooks (per-tenant, no auth — validated by signature/token)
    path("indiamart/", IndiaMArtWebhookView.as_view(), name="api_indiamart_webhook"),
    # Click-to-WhatsApp (WhatsApp Business Platform) — must precede "meta/".
    path("meta/whatsapp/", MetaWhatsAppWebhookView.as_view(), name="api_meta_whatsapp_webhook"),
    # "Continue with Facebook" (Lead Ads through the platform's Meta app)
    path("meta/connect/", MetaConnectStatusView.as_view(), name="api_meta_connect"),
    path("meta/connect/start/", MetaConnectStartView.as_view(), name="api_meta_connect_start"),
    path("meta/connect/fetch/", MetaConnectFetchView.as_view(), name="api_meta_connect_fetch"),
    path("meta/connect/pages/<str:page_id>/", MetaConnectPageView.as_view(), name="api_meta_connect_page"),
    path("meta/connect/pages/<str:page_id>/<str:action>/", MetaConnectPageActionView.as_view(),
         name="api_meta_connect_page_action"),
    path("meta/connect/forms/<str:form_id>/", MetaConnectFormView.as_view(), name="api_meta_connect_form"),
    path("meta/forms/", MetaFormFieldsView.as_view(), name="api_meta_forms"),
    path("meta/sync/", MetaSyncLeadsView.as_view(), name="api_meta_sync"),
    path("meta/", MetaLeadAdsWebhookView.as_view(), name="api_meta_webhook"),
    path("google/", GoogleAdsWebhookView.as_view(), name="api_google_webhook"),
    path("webhook/<str:token>/", GenericWebhookView.as_view(), name="api_generic_webhook"),

    # Integration management (authenticated)
    path("configs/", IntegrationConfigListView.as_view(), name="api_integration_configs"),
    path("configs/<int:pk>/", IntegrationConfigDetailView.as_view(), name="api_integration_config_detail"),
    path("logs/", WebhookLogListView.as_view(), name="api_webhook_logs"),
]
