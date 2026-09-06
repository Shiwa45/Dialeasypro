"""
TeleCRM Backend — apps/core/utils.py

Utility functions used across the TeleCRM platform.

Sections:
  - Tenant utilities
  - Phone number utilities
  - Indian phone/GST validation
  - Schema-switching helpers (for Celery tasks)
  - General helpers
"""
import hashlib
import logging
import re
import secrets
import string
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)


# ============================================================
# Phone Number Utilities (Indian market focus)
# ============================================================

def normalize_indian_phone(phone: str) -> Optional[str]:
    """
    Normalize a phone number to E.164 format.
    Supports Indian mobile numbers (+91) as well as 7–15 digit numbers.
    """
    if not phone:
        return None

    s = str(phone).strip()
    digits_only = re.sub(r"\D", "", s)
    if not digits_only:
        return None

    if digits_only.startswith("91") and len(digits_only) == 12:
        return f"+{digits_only}"
    elif digits_only.startswith("0") and len(digits_only) == 11:
        return f"+91{digits_only[1:]}"
    elif len(digits_only) == 10:
        return f"+91{digits_only}"
    elif 7 <= len(digits_only) <= 15:
        return f"+{digits_only}"

    return None


def mask_phone_number(phone: str) -> str:
    """
    Mask phone number for logs: +919876543210 → +91XXXXXX3210
    """
    if not phone or len(phone) < 4:
        return "****"
    return phone[:-4].replace(phone[:-4], "X" * len(phone[:-4])) + phone[-4:]


def validate_gstin(gstin: str) -> bool:
    """
    Validate Indian GSTIN format.
    Format: 2-digit state code + 10-digit PAN + 1-digit entity + 1-Z + 1-checksum
    Total: 15 characters
    Example: 27AAPFU0939F1ZV
    """
    if not gstin:
        return True  # GSTIN is optional
    pattern = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
    return bool(re.match(pattern, gstin.upper()))


def validate_indian_pin(pincode: str) -> bool:
    """Validate 6-digit Indian PIN code."""
    return bool(re.match(r"^\d{6}$", str(pincode)))


# ============================================================
# Schema / Tenant Utilities (for Celery tasks)
# ============================================================

class TenantSchemaContext:
    """
    Context manager to execute code within a specific tenant's schema.

    Essential for Celery tasks which don't have an HTTP request
    to set the schema automatically.

    Usage:
        with TenantSchemaContext('acme_realty'):
            leads = Lead.objects.all()  # queries acme_realty schema
    """

    def __init__(self, schema_name: str):
        self.schema_name = schema_name
        self._previous_schema = None

    def __enter__(self):
        self._previous_schema = connection.schema_name
        connection.set_schema(self.schema_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        connection.set_schema(self._previous_schema)
        return False  # Don't suppress exceptions


def get_all_tenant_schemas() -> list:
    """
    Get all active tenant schema names (excluding public).
    Used in Celery beat tasks to iterate over all tenants.
    """
    try:
        from apps.tenants.models import Tenant
        from apps.core.constants import SubscriptionStatus

        # Query from public schema
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO public")

        # Use the denormalized subscription_status field — avoids joining
        # through the Subscription FK which can fail when run in tenant schema context.
        return list(
            Tenant.objects.filter(
                is_active=True,
                subscription_status__in=SubscriptionStatus.ACTIVE_STATUSES,
            )
            .exclude(schema_name="public")
            .values_list("schema_name", flat=True)
        )
    except Exception as exc:
        logger.error(f"Failed to get tenant schemas: {exc}")
        return []


def run_for_all_tenants(func, *args, **kwargs):
    """
    Execute a function for all active tenants.

    Usage in Celery task:
        def my_task():
            run_for_all_tenants(process_followups_for_tenant)

    def process_followups_for_tenant(schema_name):
        with TenantSchemaContext(schema_name):
            ...
    """
    schemas = get_all_tenant_schemas()
    results = {}
    for schema_name in schemas:
        try:
            results[schema_name] = func(schema_name, *args, **kwargs)
        except Exception as exc:
            logger.error(f"Error processing tenant {schema_name}: {exc}")
            results[schema_name] = {"error": str(exc)}
    return results


# ============================================================
# Token / Secret Generation
# ============================================================

def generate_webhook_secret(length: int = 32) -> str:
    """Generate a secure random webhook secret for tenant integrations."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_api_key(prefix: str = "tcrm") -> str:
    """
    Generate a unique API key for tenant API access.
    Format: tcrm_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    """
    random_part = secrets.token_hex(24)
    return f"{prefix}_live_{random_part}"


def hash_api_key(api_key: str) -> str:
    """Hash an API key for safe storage. Store the hash, not the raw key."""
    return hashlib.sha256(api_key.encode()).hexdigest()


# ============================================================
# Pagination Helpers
# ============================================================

def paginate_queryset(queryset, page: int, page_size: int = 25):
    """
    Simple pagination for non-DRF views (MVT).
    Returns (page_data, total_count, total_pages, has_next, has_prev)
    """
    total_count = queryset.count()
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = max(1, min(page, total_pages))

    start = (page - 1) * page_size
    end = start + page_size

    return {
        "data": queryset[start:end],
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


# ============================================================
# Slug Generation
# ============================================================

def slugify_company_name(name: str) -> str:
    """
    Convert company name to a valid PostgreSQL schema name.
    Schema names must be lowercase, start with letter, contain only
    letters, digits, and underscores. Max 63 chars.

    'Acme Realty Pvt Ltd' → 'acme_realty_pvt_ltd'
    'ABC Corp.' → 'abc_corp'
    """
    # Convert to lowercase
    slug = name.lower()
    # Replace spaces and hyphens with underscores
    slug = re.sub(r"[\s\-]+", "_", slug)
    # Remove non-alphanumeric characters (except underscore)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    # Remove leading digits or underscores (schema must start with letter)
    slug = re.sub(r"^[0-9_]+", "", slug)
    # Truncate to 55 chars (leaving room for suffix if needed)
    slug = slug[:55]
    # Remove trailing underscores
    slug = slug.rstrip("_")
    return slug or "tenant"


def make_unique_schema_name(base_name: str) -> str:
    """
    Ensure the schema name is unique across all tenants.
    Appends a numeric suffix if needed: acme → acme_2 → acme_3
    """
    from apps.tenants.models import Tenant

    slug = slugify_company_name(base_name)
    candidate = slug
    counter = 2

    while Tenant.objects.filter(schema_name=candidate).exists():
        candidate = f"{slug}_{counter}"
        counter += 1

    return candidate


# ============================================================
# Template / Email Utilities
# ============================================================

def render_template_with_variables(template_content: str, variables: dict) -> str:
    """
    Replace {{variable_name}} placeholders in a template string.
    Used for WhatsApp template variable substitution.

    Example:
        template = "Hello {{lead_name}}, your property at {{location}} is ready."
        variables = {"lead_name": "Rahul", "location": "Bandra West"}
        result = "Hello Rahul, your property at Bandra West is ready."
    """
    for key, value in variables.items():
        template_content = template_content.replace(f"{{{{{key}}}}}", str(value or ""))
    return template_content


# ============================================================
# Cache Key Helpers
# ============================================================

def tenant_cache_key(schema_name: str, key: str) -> str:
    """Generate a tenant-scoped cache key."""
    return f"t:{schema_name}:{key}"


def get_cached_or_compute(cache_key: str, compute_fn, timeout: int = 300):
    """
    Get from cache or compute and cache.

    Usage:
        data = get_cached_or_compute(
            key="lead_stats",
            compute_fn=lambda: expensive_query(),
            timeout=300
        )
    """
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = compute_fn()
    cache.set(cache_key, result, timeout=timeout)
    return result


# ============================================================
# Indian GST Calculation
# ============================================================

from decimal import ROUND_HALF_UP, Decimal


def gst_from_inclusive(total_amount, customer_state: str) -> dict:
    """
    Split an amount the customer has ALREADY paid into base + GST.

    calculate_gst() goes the other way: it adds tax on top of a pre-tax figure.
    Feeding it a Razorpay charge — which is the gross the card was debited —
    produced an invoice 18% larger than the payment it documents, which is a
    GST filing problem, not a display bug.

    The base is back-computed and the components are then derived from it, with
    any rounding remainder pushed into the base so base + GST equals the amount
    charged to the rupee. An invoice that does not reconcile with its payment
    is worse than one that is a paisa off on the split.
    """
    from apps.core.constants import GSTState

    gross = Decimal(str(total_amount))
    info = GSTState.get_gst_components(customer_state)
    rate = Decimal(str(info["igst_rate"] if info["is_interstate"] else
                       info["cgst_rate"] + info["sgst_rate"]))

    two = Decimal("0.01")
    base = (gross / (1 + rate / 100)).quantize(two, rounding=ROUND_HALF_UP)

    if info["is_interstate"]:
        igst = (gross - base).quantize(two, rounding=ROUND_HALF_UP)
        return {
            "base_amount": base,
            "cgst_rate": 0, "sgst_rate": 0, "igst_rate": info["igst_rate"],
            "cgst_amount": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_amount": igst,
            "total_gst": igst,
            "total_amount": gross,
            "is_interstate": True,
        }

    total_gst = (gross - base).quantize(two, rounding=ROUND_HALF_UP)
    # Halve the tax, giving any odd paisa to CGST so the two still sum exactly.
    cgst = (total_gst / 2).quantize(two, rounding=ROUND_HALF_UP)
    sgst = (total_gst - cgst).quantize(two, rounding=ROUND_HALF_UP)
    return {
        "base_amount": base,
        "cgst_rate": info["cgst_rate"], "sgst_rate": info["sgst_rate"], "igst_rate": 0,
        "cgst_amount": cgst,
        "sgst_amount": sgst,
        "igst_amount": Decimal("0.00"),
        "total_gst": total_gst,
        "total_amount": gross,
        "is_interstate": False,
    }


def calculate_gst(base_amount: Decimal, customer_state: str) -> dict:
    """
    Calculate GST components for an invoice.

    Args:
        base_amount: Pre-tax amount in INR
        customer_state: 2-letter Indian state code (e.g., "MH", "DL")

    Returns:
        dict with cgst_amount, sgst_amount, igst_amount, total_amount
    """
    from apps.core.constants import GSTState

    gst_info = GSTState.get_gst_components(customer_state)
    base = Decimal(str(base_amount))

    two_places = Decimal("0.01")

    if gst_info["is_interstate"]:
        igst = (base * Decimal(str(gst_info["igst_rate"])) / 100).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        return {
            "base_amount": base,
            "cgst_rate": 0,
            "sgst_rate": 0,
            "igst_rate": gst_info["igst_rate"],
            "cgst_amount": Decimal("0.00"),
            "sgst_amount": Decimal("0.00"),
            "igst_amount": igst,
            "total_gst": igst,
            "total_amount": base + igst,
            "is_interstate": True,
        }
    else:
        cgst = (base * Decimal("9") / 100).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        sgst = (base * Decimal("9") / 100).quantize(
            two_places, rounding=ROUND_HALF_UP
        )
        total_gst = cgst + sgst
        return {
            "base_amount": base,
            "cgst_rate": 9,
            "sgst_rate": 9,
            "igst_rate": 0,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "igst_amount": Decimal("0.00"),
            "total_gst": total_gst,
            "total_amount": base + total_gst,
            "is_interstate": False,
        }
