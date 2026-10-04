"""
TeleCRM Backend — apps/integrations/signals.py

Browser access to the generic webhook from any website.

A tenant's website form (a static marketing site, a landing page builder)
posts leads straight from the visitor's browser to
/api/v1/integrations/webhook/<token>/. CORS is otherwise limited to the CRM's
own domains, so the browser refused every such submission unless the site's
domain had been added to the server's CORS_ALLOWED_ORIGINS — a server change
for each customer's website.

Allowing any origin on that one path is safe: it is authenticated by the
secret token in its URL alone. It reads no cookies or session and returns no
data, so a page on another site gains nothing it could not do with the token
from any HTTP client. Every other endpoint keeps the strict origin list.
"""
import re

from corsheaders.signals import check_request_enabled
from django.dispatch import receiver

# The generic webhook only. Provider webhooks (Meta, Google, IndiaMART) are
# called server to server and need no browser access.
_WEBSITE_WEBHOOK_PATH = re.compile(r"^/api/v1/integrations/webhook/[^/]+/?$")


@receiver(check_request_enabled)
def allow_website_forms(sender, request, **kwargs):
    return bool(_WEBSITE_WEBHOOK_PATH.match(request.path))
