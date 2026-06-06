"""
TeleCRM Backend — config/settings/development.py

Development environment settings.
Overrides base.py for local development.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---- Development: Allow unknown domains to fall through to public schema ----
# In production all tenant domains are properly registered.  In development
# mobile apps use IPs (10.0.2.2, 192.168.x.x) that are not in the Domain
# table.  Setting this True makes TenantMainMiddleware route those requests
# to the public schema instead of raising Http404, which lets our
# TenantSchemaFromTokenMiddleware correct the schema via X-Workspace-Id header.
SHOW_PUBLIC_IF_NO_TENANT_FOUND = True

# ---- Development: Show all CORS origins --------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---- Development: Email to console -------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---- Development: No S3 — use local storage ----------------
USE_S3 = False
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# ---- Development: Django Debug Toolbar ---------------------
try:
    import debug_toolbar  # noqa: F401
    INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
    MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405
    INTERNAL_IPS = ["127.0.0.1", "::1", "0.0.0.0"]
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: True,
        "SHOW_COLLAPSED": True,
    }
except ImportError:
    pass

# ---- Development: Log SQL queries --------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] [{levelname}] [{name}] {message}",
            "style": "{",
            "datefmt": "%H:%M:%S",
        },
        "sql": {
            "format": "[SQL] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Uncomment to log ALL SQL queries (very verbose):
        # "django.db.backends": {
        #     "handlers": ["console"],
        #     "level": "DEBUG",
        #     "propagate": False,
        # },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
}

# ---- Development: Celery runs tasks synchronously (optional) ---
# Set to True to skip Celery and run tasks inline (easier debugging)
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = True

# ---- Development: Disable CSRF for API testing (DANGER: dev only!) ---
# REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] also has SessionAuthentication
# which requires CSRF. Comment the line below if you want CSRF in dev.
# CSRF_TRUSTED_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]

# ---- Development: Looser password validation ---------------
AUTH_PASSWORD_VALIDATORS = []

# ---- Development: Shorter JWT for testing ------------------
# Uncomment to make tokens expire faster for testing:
# from datetime import timedelta
# SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"] = timedelta(minutes=5)

print("⚡ TeleCRM running in DEVELOPMENT mode")
