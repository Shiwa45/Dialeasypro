"""
TeleCRM Backend — apps/integrations/management/commands/test_webhook.py

Send a test payload to the local webhook endpoint for a specific source.

Usage:
    python manage.py test_webhook --schema=acme_realty --source=indiamart
    python manage.py test_webhook --schema=acme_realty --source=generic --token=<webhook_token>
"""
import json
import requests
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test webhook payload to an integration endpoint."

    def add_arguments(self, parser):
        parser.add_argument("--schema", required=True, type=str)
        parser.add_argument("--source", required=True, type=str,
                            choices=["indiamart", "meta", "google", "generic"])
        parser.add_argument("--token", type=str, default="", help="Webhook token (for generic)")
        parser.add_argument("--host", type=str, default="http://localhost:8000")

    def handle(self, *args, **options):
        schema = options["schema"]
        source = options["source"]
        host = options["host"]

        test_payloads = {
            "indiamart": {
                "SENDER_NAME": "Test Lead From IndiaMART",
                "MOBILE_NUMBER": "9876543210",
                "SENDER_EMAIL": "test@indiamart.com",
                "CITY": "Mumbai",
                "SUBJECT": "Looking for property in Bandra",
                "UNIQUE_QUERY_ID": f"IMTEST{__import__('random').randint(1000,9999)}",
            },
            "meta": {
                "object": "page",
                "entry": [{
                    "changes": [{
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": "12345678",
                            "form_id": "87654321",
                            "page_id": "11111111",
                        },
                    }],
                }],
            },
            "google": {
                "first_name": "Test",
                "last_name": "Google Lead",
                "phone_number": "9876543210",
                "email": "testgoogle@example.com",
                "city": "Delhi",
                "message": "Interested in 3BHK",
            },
            "generic": {
                "name": "Test Generic Lead",
                "phone": "9123456789",
                "email": "generic@test.com",
                "city": "Bangalore",
                "message": "Test lead via generic webhook",
            },
        }

        payload = test_payloads[source]
        if source == "generic":
            token = options["token"]
            url = f"{host}/api/v1/integrations/webhook/{token}/"
        else:
            url = f"{host}/api/v1/integrations/{source}/"

        self.stdout.write(f"POST {url}")
        self.stdout.write(f"Payload: {json.dumps(payload, indent=2)}")

        try:
            resp = requests.post(url, json=payload, timeout=10,
                                 headers={"X-Tenant-Schema": schema})
            self.stdout.write(f"Response: {resp.status_code} — {resp.text[:200]}")
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Request failed: {exc}"))
