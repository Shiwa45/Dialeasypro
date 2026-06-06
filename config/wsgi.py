"""
TeleCRM Backend — config/wsgi.py

WSGI application entry point.
Used for traditional HTTP deployments (gunicorn).
For WebSocket support, use asgi.py with Daphne.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

application = get_wsgi_application()
