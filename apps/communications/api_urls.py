"""TeleCRM Backend — apps/communications/api_urls.py"""
from django.urls import path
from apps.communications.views import (
    WhatsAppTemplateListView, WhatsAppMessageListView,
    SendWhatsAppView, SendSMSView,
    BulkCampaignListCreateView, BulkCampaignDetailView,
    BulkCampaignLaunchView, BulkCampaignPauseView,
    WhatsAppWebhookView, TemplateMediaUploadView,
    WhatsAppConfigView, WhatsAppConfigTestView,
    WhatsAppVerifyTokenView, WhatsAppConversationListView,
)

urlpatterns = [
    path("whatsapp/config/", WhatsAppConfigView.as_view(), name="api_wa_config"),
    path("whatsapp/config/test/", WhatsAppConfigTestView.as_view(), name="api_wa_config_test"),
    path("whatsapp/webhook-token/", WhatsAppVerifyTokenView.as_view(), name="api_wa_verify_token"),
    path("whatsapp/conversations/", WhatsAppConversationListView.as_view(), name="api_wa_conversations"),
    path("whatsapp/templates/", WhatsAppTemplateListView.as_view(), name="api_wa_templates"),
    path("template-media/", TemplateMediaUploadView.as_view(), name="api_template_media"),
    path("whatsapp/messages/", WhatsAppMessageListView.as_view(), name="api_wa_messages"),
    path("whatsapp/send/", SendWhatsAppView.as_view(), name="api_wa_send"),
    path("sms/send/", SendSMSView.as_view(), name="api_sms_send"),
    path("campaigns/", BulkCampaignListCreateView.as_view(), name="api_campaigns"),
    path("campaigns/<uuid:pk>/", BulkCampaignDetailView.as_view(), name="api_campaign_detail"),
    path("campaigns/<uuid:pk>/launch/", BulkCampaignLaunchView.as_view(), name="api_campaign_launch"),
    path("campaigns/<uuid:pk>/pause/", BulkCampaignPauseView.as_view(), name="api_campaign_pause"),
    path("webhook/whatsapp/<str:provider>/", WhatsAppWebhookView.as_view(), name="api_wa_webhook"),
]
