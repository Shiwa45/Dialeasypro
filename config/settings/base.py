"""
TeleCRM Backend — config/settings/base.py

Base settings shared across all environments.
Environment-specific overrides go in development.py, production.py, testing.py.
"""
import os
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ============================================================
# Paths
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ============================================================
# Security
# ============================================================
SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*", cast=Csv())

# Key for at-rest encryption of sensitive model fields (WhatsApp provider
# credentials via apps.core.crypto). A urlsafe-base64 Fernet key — generate one
# with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# If unset, a key is derived from SECRET_KEY so dev works with no config; set it
# explicitly in production so rotating SECRET_KEY doesn't orphan stored secrets.
FIELD_ENCRYPTION_KEY = config("FIELD_ENCRYPTION_KEY", default="")

# ============================================================
# django-tenants: Multi-Tenant Configuration
# CRITICAL: SHARED_APPS must come before TENANT_APPS in INSTALLED_APPS
# Public schema tables: tenants, plans, super admin, auth
# Tenant schema tables: agents, leads, calls, etc.
# ============================================================

SHARED_APPS = [
    # django-tenants must be first
    "django_tenants",

    # Unfold (MUST be before django.contrib.admin to override templates and admin site properly)
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "unfold.contrib.import_export",

    # Django built-ins (all in public schema)
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.admin",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party (shared)
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_celery_beat",
    "django_celery_results",
    "django_filters",

    # Local — shared (public schema)
    "apps.core",
    "apps.tenants",
    "apps.plans",
    "apps.superadmin",
]

TENANT_APPS = [
    # These apps get tables in EACH tenant's schema
    "apps.authentication",
    "apps.leads",           # Phase 2
    "apps.calls",           # Phase 2
    "apps.communications",  # Phase 3
    "apps.integrations",    # Phase 3
    "apps.reports",         # Phase 3 — no DB tables, but needs Django app registration
    "apps.hrms",            # Add-on module (ModuleKey.HRMS)
    "apps.erp",             # Add-on module (ModuleKey.ERP_SALES)
    "apps.ai",              # Add-on module (ModuleKey.AI_SUITE)
]

# django-tenants requires this exact format:
INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

# ============================================================
# django-tenants Model References
# ============================================================
TENANT_MODEL = "tenants.Tenant"
TENANT_DOMAIN_MODEL = "tenants.Domain"

# URL conf for the public schema (super admin, landing page)
PUBLIC_SCHEMA_URLCONF = "config.urls_public"

# If no tenant found for domain, show public site instead of 404
SHOW_PUBLIC_IF_NO_TENANT_FOUND = True

# Tenant subdomain auto-creation
TENANT_SUBFOLDER_PREFIX = None  # We use subdomain routing, not subfolders

# ============================================================
# Middleware
# TenantMainMiddleware MUST be first to identify tenant
# ============================================================
MIDDLEWARE = [
    # django-tenants: identifies tenant from domain, sets schema
    "django_tenants.middleware.main.TenantMainMiddleware",

    # Security
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    # CORS (must be before CommonMiddleware)
    "corsheaders.middleware.CorsMiddleware",

    # Standard Django
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Custom TeleCRM middleware
    # Corrects the DB schema from the JWT token for API requests.
    # Must run BEFORE TenantFeatureFlagMiddleware so feature checks use the
    # right schema (fixes dev subdomains like demo.localhost that aren't in
    # the Domain table).
    "apps.core.middleware.TenantSchemaFromTokenMiddleware",
    "apps.core.middleware.TenantFeatureFlagMiddleware",
    "apps.core.middleware.RequestTimingMiddleware",
    "apps.superadmin.middleware.AuditLogMiddleware",
]

# ============================================================
# URL Configuration
# ROOT_URLCONF = tenant-specific URLs
# PUBLIC_SCHEMA_URLCONF = super admin / public site URLs
# ============================================================
ROOT_URLCONF = "config.urls"

# ============================================================
# Templates
# ============================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Custom context processors
                "apps.core.context_processors.tenant_context",
                "apps.core.context_processors.plan_features_context",
            ],
        },
    },
]

# ============================================================
# WSGI / ASGI
# ============================================================
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ============================================================
# Database — PostgreSQL with django-tenants backend
# ============================================================
DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": config("DB_NAME", default="telecrm_db"),
        "USER": config("DB_USER", default="telecrm_user"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "connect_timeout": 10,
        },
    }
}

# REQUIRED: django-tenants router handles cross-schema queries
DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]

# ============================================================
# Cache — Redis
# ============================================================
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "telecrm",
        "TIMEOUT": 300,  # 5 minutes default
    }
}

# Use Redis for sessions (improves performance vs DB sessions)
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_AGE = 86400 * 7  # 7 days
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = "telecrm_session"

# ============================================================
# Password Hashers (Argon2 is more secure than default PBKDF2)
# ============================================================
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ============================================================
# Internationalization — Indian market defaults
# ============================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"  # IST — Indian Standard Time
USE_I18N = True
USE_TZ = True
LANGUAGES = [
    ("en", "English"),
    ("hi", "Hindi"),
]

# ============================================================
# Static & Media Files
# ============================================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

# ============================================================
# File Storage (S3 via django-storages)
# USE_S3=False in development; True in production
# ============================================================
USE_S3 = config("USE_S3", default=False, cast=bool)

if USE_S3:
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="ap-south-1")
    AWS_S3_CUSTOM_DOMAIN = config("AWS_S3_CUSTOM_DOMAIN", default="")
    AWS_S3_OBJECT_PARAMETERS = {
        "CacheControl": "max-age=86400",
    }
    AWS_DEFAULT_ACL = "private"
    AWS_S3_FILE_OVERWRITE = False
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = config("AWS_S3_PRESIGNED_EXPIRY", default=3600, cast=int)

    # Separate buckets for public (thumbnails) and private (recordings)
    AWS_PRIVATE_BUCKET_NAME = config(
        "AWS_PRIVATE_BUCKET_NAME", default=AWS_STORAGE_BUCKET_NAME
    )

    DEFAULT_FILE_STORAGE = "apps.core.storage.MediaStorage"
    PRIVATE_FILE_STORAGE = "apps.core.storage.PrivateMediaStorage"
    STATICFILES_STORAGE = "apps.core.storage.StaticStorage"

# ============================================================
# Cloudinary (call recordings & media uploads)
# Used for storing call-recording audio uploaded from the mobile app.
# ============================================================
CLOUDINARY_CLOUD_NAME = config("CLOUDINARY_CLOUD_NAME", default="")
CLOUDINARY_API_KEY = config("CLOUDINARY_API_KEY", default="")
CLOUDINARY_API_SECRET = config("CLOUDINARY_API_SECRET", default="")
# Folder under which recordings are organised in Cloudinary.
CLOUDINARY_RECORDINGS_FOLDER = config(
    "CLOUDINARY_RECORDINGS_FOLDER", default="call_recordings"
)
CLOUDINARY_CONFIGURED = bool(
    CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET
)

# ============================================================
# Django REST Framework
# ============================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.authentication.backends.AgentJWTAuthentication",
        # Also allow session auth for browsable API in development
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.authentication.permissions.IsAuthenticatedAgent",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/hour",
        "user": "1000/hour",
        "login": "10/minute",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "rest_framework.openapi.AutoSchema",
    "NON_FIELD_ERRORS_KEY": "error",
}

# ============================================================
# JWT Configuration (djangorestframework-simplejwt)
# We use this for token infrastructure but authenticate
# against Agent model (not auth.User) — see authentication/backends.py
# ============================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=60, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=30, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "agent_id",  # We store agent_id in JWT, not user_id
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
}

# ============================================================
# CORS — Cross Origin Resource Sharing
# Mobile app needs API access from different origin
# ============================================================
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_ALL_ORIGINS = DEBUG  # Only allow all origins in DEBUG mode
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://[\w-]+\.telecrm\.in$",
    r"^https://[\w-]+\.dialeasypro\.easyian\.com$",
    r"^https://dialeasypro\.easyian\.com$",
    r"^https://[\w-]+\.easyian\.shop$",
    r"^https://easyian\.shop$",
    r"^https://[\w-]+\.vercel\.app$",
]
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-tenant-schema",  # Custom header for tenant identification
    "x-workspace-id",
]

# ============================================================
# Celery Configuration
# ============================================================
CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = config(
    "CELERY_RESULT_BACKEND", default="redis://localhost:6379/2"
)
CELERY_ACCEPT_CONTENT = ["application/json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = config("CELERY_TIMEZONE", default="Asia/Kolkata")
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes max per task
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # Soft limit: 25 minutes
CELERY_RESULT_EXPIRES = 86400  # Results expire after 24 hours

# Queue routing — separate queues for different task types
CELERY_TASK_ROUTES = {
    # Bulk operations (WhatsApp, Email, SMS campaigns)
    "apps.*.tasks.send_bulk_*": {"queue": "bulk_ops"},
    "apps.*.tasks.process_bulk_*": {"queue": "bulk_ops"},
    # Push notifications
    "apps.*.tasks.send_notification*": {"queue": "notifications"},
    "apps.*.tasks.send_push_*": {"queue": "notifications"},
    # Lead source integrations (IndiaMART, Meta, etc.)
    "apps.integrations.tasks.*": {"queue": "integrations"},
    # Call recording uploads
    "apps.calls.tasks.upload_*": {"queue": "call_uploads"},
    # Default queue for everything else
    "apps.*": {"queue": "default"},
}

CELERY_TASK_DEFAULT_QUEUE = "default"

# django-celery-beat: use database scheduler
DJANGO_CELERY_BEAT_TZ_AWARE = True

# ============================================================
# Django Channels (WebSocket for real-time features)
# Used for: live agent monitoring, real-time notifications
# ============================================================
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
            "capacity": 1500,
            "expiry": 10,
        },
    },
}

# ============================================================
# Email Configuration
# ============================================================
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="TeleCRM <noreply@telecrm.in>")
SUPPORT_EMAIL = config("SUPPORT_EMAIL", default="support@telecrm.in")

# ============================================================
# Phase 3: Communication Provider Settings
# ============================================================

# WhatsApp — Interakt (primary provider)
INTERAKT_API_KEY = config("INTERAKT_API_KEY", default="")

# WhatsApp — AiSensy (secondary)
AISENSY_API_KEY = config("AISENSY_API_KEY", default="")

# SMS — MSG91
MSG91_AUTH_KEY = config("MSG91_AUTH_KEY", default="")
MSG91_SENDER_ID = config("MSG91_SENDER_ID", default="TELCRM")

# SMS — TextLocal
TEXTLOCAL_API_KEY = config("TEXTLOCAL_API_KEY", default="")

# Meta (Facebook) Lead Ads
META_APP_SECRET = config("META_APP_SECRET", default="")
META_VERIFY_TOKEN = config("META_VERIFY_TOKEN", default="meta_webhook_verify_token")

# Google Ads (for Lead Form webhook signature validation)
GOOGLE_ADS_DEVELOPER_TOKEN = config("GOOGLE_ADS_DEVELOPER_TOKEN", default="")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ============================================================
# AI Suite (ModuleKey.AI_SUITE)
# ============================================================
# Google Gemini powers both halves of the pipeline: it reads the call audio
# directly (transcription) and then the transcript (insights). Leave the key
# empty and the whole module stays dormant — recordings sit at "pending" and
# nothing is billed.
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
GEMINI_MODEL = config("GEMINI_MODEL", default="gemini-2.5-flash")
# Transcription is the expensive half (audio tokens). Point it at a cheaper or
# stronger model independently if you need to; defaults to GEMINI_MODEL.
GEMINI_TRANSCRIBE_MODEL = config("GEMINI_TRANSCRIBE_MODEL", default="")

# ============================================================
# Razorpay (Payment Gateway — India)
# ============================================================
RAZORPAY_KEY_ID = config("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = config("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = config("RAZORPAY_WEBHOOK_SECRET", default="")

# ============================================================
# Platform Configuration
# ============================================================
BASE_DOMAIN = config("BASE_DOMAIN", default="telecrm.in")
# All root domains that tenants should be registered on.
# When a new tenant is created, a Domain row is created for each entry.
# This enables the gradual migration from dialeasypro.easyian.com → easyian.shop.
BASE_DOMAINS = config(
    "BASE_DOMAINS",
    default=BASE_DOMAIN,
    cast=lambda v: [d.strip() for d in v.split(",") if d.strip()],
)
SUPER_ADMIN_DOMAIN = config("SUPER_ADMIN_DOMAIN", default="admin.telecrm.in")
DEFAULT_TRIAL_DAYS = config("DEFAULT_TRIAL_DAYS", default=14, cast=int)
MAINTENANCE_MODE = config("MAINTENANCE_MODE", default=False, cast=bool)
ALLOW_NEW_REGISTRATIONS = config("ALLOW_NEW_REGISTRATIONS", default=True, cast=bool)

# Meta / Facebook Webhook Verification Token
META_WHATSAPP_VERIFY_TOKEN = config("META_WHATSAPP_VERIFY_TOKEN", default="")

# TRAI DND (Do Not Disturb) registry
TRAI_DND_ENABLED = config("TRAI_DND_ENABLED", default=False, cast=bool)
TRAI_DND_API_KEY = config("TRAI_DND_API_KEY", default="")
TRAI_DND_API_URL = config(
    "TRAI_DND_API_URL", default="https://api.ndnc.org.in/scrubber/"
)

# ============================================================
# Default Auto Field
# ============================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ============================================================
# Admin URL (change from default to reduce automated attacks)
# ============================================================
ADMIN_URL = "superadmin/"

# ============================================================
# Logging Configuration
# ============================================================
LOG_LEVEL = config("LOG_LEVEL", default="INFO")
LOG_FILE = config("LOG_FILE", default="/var/log/telecrm/app.log")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] [{levelname}] [{name}] [{process:d}] {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "[{levelname}] {message}",
            "style": "{",
        },
        "json": {
            "()": "apps.core.logging.JsonFormatter",
        },
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
        "require_debug_true": {"()": "django.utils.log.RequireDebugTrue"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": True,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",  # Change to DEBUG to log all queries
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}

# ============================================================
# Sentry (Error Monitoring — configured in production settings)
# ============================================================
SENTRY_DSN = config("SENTRY_DSN", default="")

# ============================================================
# Django-Unfold Admin Theme Configuration
# ============================================================
from django.templatetags.static import static  # noqa: E402
from django.urls import reverse_lazy  # noqa: E402


def environment_callback(request):
    """Show environment badge in admin."""
    return ["Development", "warning"] if DEBUG else ["Production", "success"]


UNFOLD = {
    "SITE_TITLE": "TeleCRM",
    "SITE_HEADER": "TeleCRM Super Admin",
    "SITE_URL": "/",
    "SITE_SYMBOL": "cell_tower",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": True,
    "ENVIRONMENT": "config.settings.base.environment_callback",
    "DASHBOARD_CALLBACK": "apps.superadmin.views.superadmin_dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": "Dashboard",
                "items": [
                    {
                        "title": "Dashboard",
                        "icon": "dashboard",
                        "link": reverse_lazy("admin:index"),
                    }
                ]
            },
            {
                "separator": True,
                "title": "Tenant Management",
                "collapsible": True,
                "items": [
                    {
                        "title": "Tenants",
                        "icon": "domain",
                        "link": reverse_lazy("admin:tenants_tenant_changelist"),
                    },
                    {
                        "title": "Domains",
                        "icon": "language",
                        "link": reverse_lazy("admin:tenants_domain_changelist"),
                    },
                ],
            },
            {
                "separator": True,
                "title": "Plans & Billing",
                "collapsible": True,
                "items": [
                    {
                        "title": "Plans",
                        "icon": "card_membership",
                        "link": reverse_lazy("admin:plans_plan_changelist"),
                    },
                    {
                        "title": "Plan Features",
                        "icon": "tune",
                        "link": reverse_lazy("admin:plans_planfeature_changelist"),
                    },
                    {
                        "title": "Subscriptions",
                        "icon": "subscriptions",
                        "link": reverse_lazy("admin:plans_subscription_changelist"),
                    },
                    {
                        "title": "Invoices",
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:plans_invoice_changelist"),
                    },
                ],
            },
            {
                "separator": True,
                "title": "System",
                "collapsible": True,
                "items": [
                    {
                        "title": "Audit Logs",
                        "icon": "manage_search",
                        "link": reverse_lazy("admin:superadmin_auditlog_changelist"),
                    },
                    {
                        "title": "Global Settings",
                        "icon": "settings",
                        "link": reverse_lazy(
                            "admin:superadmin_globalsettings_changelist"
                        ),
                    },
                    {
                        "title": "Scheduled Tasks",
                        "icon": "schedule",
                        "link": reverse_lazy(
                            "admin:django_celery_beat_periodictask_changelist"
                        ),
                    },
                ],
            },
            {
                "separator": True,
                "title": "Auth",
                "collapsible": True,
                "items": [
                    {
                        "title": "Super Admin Users",
                        "icon": "admin_panel_settings",
                        "link": reverse_lazy("admin:auth_user_changelist"),
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                    },
                ],
            },
        ],
    },
}

# ============================================================
# Content Security Policy Headers
# ============================================================
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "SAMEORIGIN"
SECURE_CONTENT_TYPE_NOSNIFF = True
