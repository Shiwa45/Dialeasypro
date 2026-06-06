"""
TeleCRM Backend — apps/communications/signals.py
Update campaign reply count when inbound WhatsApp received.
"""
import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.communications.models import WhatsAppMessage

logger = logging.getLogger(__name__)

@receiver(post_save, sender=WhatsAppMessage)
def whatsapp_message_post_save(sender, instance, created, **kwargs):
    if created and instance.direction == "inbound" and instance.campaign_id:
        from django.db.models import F
        from apps.communications.models import BulkCampaign
        BulkCampaign.objects.filter(pk=instance.campaign_id).update(
            replied_count=F("replied_count") + 1
        )
