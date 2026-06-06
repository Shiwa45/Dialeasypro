"""
TeleCRM Backend — apps/tenants/signals.py

Django signals for Tenant lifecycle events.

post_schema_sync  : Fired by django-tenants after a new tenant schema is
                    created and all migrations have run. We use this to:
                    1. Create the default tenant admin Agent
                    2. Set the trial period
                    3. Queue a welcome email

pre_delete        : Clean up before tenant deletion.
"""
import logging
import secrets
import string

from django.conf import settings
from django.db import connection
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django_tenants.signals import post_schema_sync, schema_needs_to_be_deleted

from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


@receiver(post_schema_sync, sender=Tenant)
def tenant_post_schema_sync(sender, tenant, **kwargs):
    """
    Called after a new tenant's schema is created and migrations have run.
    Sets up the initial state for a new tenant.
    """
    if tenant.schema_name == "public":
        return

    logger.info(f"[Tenant Signal] post_schema_sync for: {tenant.schema_name}")

    try:
        # 1. Set trial period
        from django.conf import settings as django_settings
        trial_days = getattr(django_settings, "DEFAULT_TRIAL_DAYS", 14)
        tenant.set_trial(days=trial_days)

        # 2. Create default tenant admin in the new schema
        _create_default_tenant_admin(tenant)

        # 3. Create default plan (starter) subscription
        _create_default_subscription(tenant)

        # 4. Seed default call dispositions
        _seed_default_dispositions(tenant)

        # 5. Queue welcome email (Celery task)
        _queue_welcome_email(tenant)

    except Exception as exc:
        logger.error(
            f"[Tenant Signal] Error in post_schema_sync for {tenant.schema_name}: {exc}",
            exc_info=True,
        )


def _create_default_tenant_admin(tenant: Tenant):
    """
    Create the first agent (tenant admin) in the new tenant schema.
    Password is auto-generated and sent via welcome email.
    """
    from apps.authentication.models import Agent
    from apps.core.constants import AgentRole

    previous_schema = connection.schema_name

    try:
        connection.set_schema(tenant.schema_name)

        # Check if any agent already exists (idempotent)
        if Agent.objects.filter(is_tenant_admin=True).exists():
            logger.info(
                f"[Tenant Signal] Admin already exists in {tenant.schema_name}, skipping."
            )
            return

        # Generate a secure temporary password
        temp_password = _generate_temp_password()

        admin_agent = Agent(
            email=tenant.primary_contact_email,
            name=tenant.primary_contact_name,
            phone=tenant.primary_contact_phone,
            role=AgentRole.ADMIN,
            is_tenant_admin=True,
            is_active=True,
            must_change_password=True,  # Force password change on first login
        )
        admin_agent.set_password(temp_password)
        admin_agent.save()

        # Store temp password on tenant for welcome email (temporary)
        tenant._temp_admin_password = temp_password

        logger.info(
            f"[Tenant Signal] Created admin agent '{tenant.primary_contact_email}' "
            f"in {tenant.schema_name}"
        )

    except Exception as exc:
        logger.error(
            f"[Tenant Signal] Failed to create admin for {tenant.schema_name}: {exc}"
        )
    finally:
        connection.set_schema(previous_schema)


def _create_default_subscription(tenant: Tenant):
    """Assign the default (Starter) plan subscription to new tenant."""
    try:
        from apps.plans.models import Plan, Subscription
        from apps.core.constants import PlanSlug, SubscriptionStatus

        starter_plan = Plan.objects.filter(
            slug=PlanSlug.STARTER, is_active=True
        ).first()

        if not starter_plan:
            logger.warning(
                f"[Tenant Signal] No starter plan found for {tenant.schema_name}"
            )
            return

        Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={
                "plan": starter_plan,
                "status": SubscriptionStatus.TRIAL,
                "trial_end": tenant.trial_ends_at,
            },
        )

        # Update tenant plan reference
        tenant.plan = starter_plan
        tenant.save(update_fields=["plan"])

        logger.info(
            f"[Tenant Signal] Assigned starter plan to {tenant.schema_name}"
        )

    except Exception as exc:
        logger.error(
            f"[Tenant Signal] Failed to create subscription for {tenant.schema_name}: {exc}"
        )


def _queue_welcome_email(tenant: Tenant):
    """Queue the welcome email to be sent via Celery."""
    try:
        from apps.tenants.tasks import send_tenant_welcome_email

        temp_password = getattr(tenant, "_temp_admin_password", None)

        send_tenant_welcome_email.apply_async(
            kwargs={
                "tenant_id": tenant.pk,
                "temp_password": temp_password,
            },
            countdown=5,  # Small delay to ensure DB commit
            queue="notifications",
        )
    except Exception as exc:
        logger.warning(f"[Tenant Signal] Could not queue welcome email: {exc}")


def _seed_default_dispositions(tenant):
    """Seed default call dispositions for a new tenant."""
    try:
        from django.core.management import call_command
        call_command("seed_dispositions", schema=tenant.schema_name, verbosity=0)
        logger.info(f"[Tenant Signal] Dispositions seeded for {tenant.schema_name}")
    except Exception as exc:
        logger.warning(f"[Tenant Signal] Could not seed dispositions: {exc}")


def _generate_temp_password(length: int = 12) -> str:
    """Generate a secure temporary password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    # Ensure at least one of each required character type
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%"),
    ]
    password += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


@receiver(pre_delete, sender=Tenant)
def tenant_pre_delete(sender, instance, **kwargs):
    """
    Clean up before tenant deletion.
    Logs the deletion for audit purposes.
    """
    if instance.schema_name == "public":
        return

    logger.warning(
        f"[Tenant Signal] Tenant being DELETED: {instance.company_name} "
        f"({instance.schema_name})"
    )
