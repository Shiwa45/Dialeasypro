"""
TeleCRM Backend — config/settings/production.py

Production environment settings.
All sensitive values via environment variables — never hardcoded.
"""
import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from .base import *  # noqa: F401, F403
from .base import SENTRY_DSN, config  # noqa: F401

DEBUG = False

# ---- Production: Strict allowed hosts ----------------------
ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv(), default="")
# E.g.: ALLOWED_HOSTS=telecrm.in,.telecrm.in,admin.telecrm.in

# ---- Production: S3 for all file storage -------------------
USE_S3 = config("USE_S3", default=True, cast=bool)

# ---- Production: Security headers --------------------------
# SECURE_SSL_REDIRECT defaults True; set to False if terminating SSL at load balancer/nginx
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ---- Production: CSRF trusted origins ----------------------
CSRF_TRUSTED_ORIGINS = [
    f"https://{config('BASE_DOMAIN', default='api.dialeasypro.easyian.com')}",
    f"https://*.{config('BASE_DOMAIN', default='api.dialeasypro.easyian.com')}",
    "https://easyian.shop",
    "https://*.easyian.shop",
]

# ---- Production: Email (AWS SES) ---------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

# ---- Production: Database connections ----------------------
# IMPORTANT: We run async UvicornWorker processes. With persistent
# connections (CONN_MAX_AGE > 0) each worker thread holds its own DB
# connection open, which quickly exhausts the RDS connection slots
# ("remaining connection slots are reserved for rds_reserved").
# Default to 0 (close after each request) and make it tunable. Use a
# connection pooler (PgBouncer / RDS Proxy) before raising this.
DATABASES["default"]["CONN_MAX_AGE"] = config(  # noqa: F405
    "DB_CONN_MAX_AGE", default=0, cast=int
)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
DATABASES["default"]["OPTIONS"] = {  # noqa: F405
    "connect_timeout": 10,
    "sslmode": config("DB_SSLMODE", default="require"),
}

# ---- Production: Stricter CORS -----------------------------
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS", default="", cast=Csv()
)

# ---- Production: Caching with longer TTLs ------------------
CACHES["default"]["TIMEOUT"] = 600  # noqa: F405 — 10 minutes in prod

# ---- Production: Sentry Error Monitoring -------------------
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(
                transaction_style="url",
                middleware_spans=True,
                signals_spans=True,
            ),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
        ],
        environment=config("SENTRY_ENVIRONMENT", default="production"),
        traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.1, cast=float),
        profiles_sample_rate=0.1,
        send_default_pii=False,  # DPDP compliance: don't send PII to Sentry
        # Ignore common non-critical errors
        ignore_errors=[
            "SystemExit",
            "KeyboardInterrupt",
        ],
    )

# ---- Production: Logging (JSON format for log aggregation) -
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.logging.JsonFormatter",
        },
        "verbose": {
            "format": "[{asctime}] [{levelname}] [{name}] [{process:d}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "include_html": False,
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console", "mail_admins"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# ---- Production: Admin URL (security through obscurity) ----
ADMIN_URL = config("ADMIN_URL", default="superadmin-secure/")
