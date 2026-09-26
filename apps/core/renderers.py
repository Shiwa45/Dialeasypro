"""
TeleCRM Backend — apps/core/renderers.py

Renderers that let a DRF view answer with something other than JSON.
"""
import json

from rest_framework.renderers import BaseRenderer


class CSVRenderer(BaseRenderer):
    """
    Lets a view accept `Accept: text/csv`.

    DRF negotiates content BEFORE the view's own code runs, so a view that
    streams a CSV still gets a 406 from a client that politely says what it
    wants — which is exactly what the CRM's Export button does. Declaring this
    renderer makes text/csv acceptable; the CSV itself is written by the view
    as a StreamingHttpResponse and never passes through here.

    What does pass through is an ERROR raised after negotiation — a plan limit
    or a permission refusal — because DRF renders those with whatever renderer
    was negotiated. Those are dicts, so they go out as JSON text rather than
    as an unreadable cast of a dict to CSV. The clients read the body as text
    and parse it, so the reason survives.
    """

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        if isinstance(data, (bytes, str)):
            return data
        return json.dumps(data, default=str)
