"""
TeleCRM Backend — config/settings/testing.py

Settings for running pytest test suite.
Uses a separate test database to avoid polluting dev data.
"""
from .base import *  # noqa: F401, F403

DEBUG = False

# ---- Testing: Use fast password hasher ---------------------
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ---- Testing: In-memory email backend ----------------------
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ---- Testing: Disable S3 -----------------------------------
USE_S3 = False
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
MEDIA_ROOT = "/tmp/telecrm_test_media/"

# ---- Testing: Celery runs synchronously --------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# ---- Testing: Use in-memory cache (no Redis needed) --------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "telecrm-test",
    }
}

# ---- Testing: Disable Channel Layers -----------------------
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

# ---- Testing: Simple session backend ----------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ---- Testing: Disable rate throttling ---------------------
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {},
}

# ---- Testing: No password validation ----------------------
AUTH_PASSWORD_VALIDATORS = []

# ---- Testing: Short JWT tokens ----------------------------
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

# ---- Testing: Disable Sentry ------------------------------
SENTRY_DSN = ""

# ---- Testing: Disable maintenance mode --------------------
MAINTENANCE_MODE = False

# ---- Testing: Test-specific database ----------------------
DATABASES["default"]["TEST"] = {  # noqa: F405
    "NAME": "test_telecrm_db",
}

# ---- Testing: Silence Django logs -------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {
        "null": {"class": "logging.NullHandler"},
    },
    "root": {
        "handlers": ["null"],
        "level": "CRITICAL",
    },
}
