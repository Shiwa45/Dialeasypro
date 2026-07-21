"""
TeleCRM Backend — apps/tenants/signals.py

Django signals for Tenant lifecycle events.

post_schema_sync  : Fired by django-tenants after a new tenant schema is
                    created and all migrations have run. We use this to:
                    1. Create the default tenant admin Agent
                    2. Set the trial period
                    3. Create default subscription + assign features
                    4. Register domains for all BASE_DOMAINS
                    5. Queue a welcome email

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

        # 4. Register domains for ALL configured root domains
        _register_tenant_domains(tenant)

        # 5. Seed default call dispositions
        _seed_default_dispositions(tenant)

        # 6. Queue welcome email (Celery task)
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

        if not tenant.primary_contact_email:
            logger.error(
                f"[Tenant Signal] Cannot create admin for {tenant.schema_name}: "
                f"no primary_contact_email set on Tenant."
            )
            return

        # Generate a secure temporary password
        temp_password = _generate_temp_password()

        admin_agent = Agent(
            email=tenant.primary_contact_email,
            name=tenant.primary_contact_name or "Admin",
            phone=getattr(tenant, "primary_contact_phone", ""),
            role=AgentRole.ADMIN,
            is_tenant_admin=True,
            is_active=True,
            must_change_password=True,  # Force password change on first login
        )
        admin_agent.set_password(temp_password)
        admin_agent.save()

        # Store temp password on tenant for welcome email (temporary in-memory attribute)
        tenant._temp_admin_password = temp_password

        logger.info(
            f"[Tenant Signal] Created admin agent '{tenant.primary_contact_email}' "
            f"in {tenant.schema_name}"
        )

    except Exception as exc:
        logger.error(
            f"[Tenant Signal] Failed to create admin for {tenant.schema_name}: {exc}",
            exc_info=True,
        )
    finally:
        connection.set_schema(previous_schema)


def _create_default_subscription(tenant: Tenant):
    """
    Assign the default (Starter) plan subscription to new tenant.
    Invalidates the feature-flag cache so features are immediately available.
    """
    try:
        from apps.plans.models import Plan, Subscription
        from apps.core.constants import PlanSlug, SubscriptionStatus

        starter_plan = Plan.objects.filter(
            slug=PlanSlug.STARTER, is_active=True
        ).first()

        if not starter_plan:
            logger.error(
                f"[Tenant Signal] No active starter plan found for {tenant.schema_name}! "
                f"Features will NOT work until a plan is assigned."
            )
            return

        subscription, created = Subscription.objects.get_or_create(
            tenant=tenant,
            defaults={
                "plan": starter_plan,
                "status": SubscriptionStatus.TRIAL,
                "trial_end": tenant.trial_ends_at,
            },
        )

        if not created:
            # Subscription already existed — make sure it's pointing to the right plan
            if subscription.status not in SubscriptionStatus.ACTIVE_STATUSES:
                subscription.status = SubscriptionStatus.TRIAL
                subscription.plan = starter_plan
                subscription.save(update_fields=["status", "plan"])
                logger.info(
                    f"[Tenant Signal] Reactivated subscription for {tenant.schema_name}"
                )

        # Update tenant plan reference
        tenant.plan = starter_plan
        tenant.save(update_fields=["plan"])

        # CRITICAL: Invalidate the feature-flag cache so the new features
        # are immediately available on the very first request.
        try:
            from apps.core.middleware import TenantFeatureFlagMiddleware
            TenantFeatureFlagMiddleware.invalidate_cache(tenant.schema_name)
        except Exception:
            pass

        logger.info(
            f"[Tenant Signal] Assigned starter plan '{starter_plan.name}' "
            f"to {tenant.schema_name} (subscription status: {subscription.status})"
        )

    except Exception as exc:
        logger.error(
            f"[Tenant Signal] Failed to create subscription for {tenant.schema_name}: {exc}",
            exc_info=True,
        )


def _register_tenant_domains(tenant: Tenant):
    """
    Register a Domain entry for each root domain in settings.BASE_DOMAINS.

    This ensures that both old (dialeasypro.easyian.com) and new (easyian.shop)
    domains resolve to this tenant, allowing a gradual migration.
    """
    from apps.tenants.models import Domain

    base_domains = getattr(settings, "BASE_DOMAINS", [settings.BASE_DOMAIN])
    is_first = True

    for root_domain in base_domains:
        domain_str = f"{tenant.schema_name}.{root_domain}"

        _, created = Domain.objects.get_or_create(
            domain=domain_str,
            defaults={
                "tenant": tenant,
                "is_primary": is_first,  # First domain is primary
            },
        )

        if created:
            logger.info(
                f"[Tenant Signal] Registered domain '{domain_str}' for "
                f"{tenant.schema_name} (primary={is_first})"
            )
        else:
            logger.info(
                f"[Tenant Signal] Domain '{domain_str}' already exists for "
                f"{tenant.schema_name}, skipping."
            )

        is_first = False


def _queue_welcome_email(tenant: Tenant):
    """Queue the welcome email to be sent via Celery."""
    try:
        from apps.tenants.tasks import send_tenant_welcome_email

        temp_password = getattr(tenant, "_temp_admin_password", None)

        if not temp_password:
            logger.warning(
                f"[Tenant Signal] No temp password available for {tenant.schema_name} "
                f"welcome email — admin may not have been created."
            )

        send_tenant_welcome_email.apply_async(
            kwargs={
                "tenant_id": tenant.pk,
                "temp_password": temp_password,
            },
            countdown=5,  # Small delay to ensure DB commit
            queue="notifications",
        )

        logger.info(
            f"[Tenant Signal] Queued welcome email for {tenant.schema_name} "
            f"to {tenant.primary_contact_email}"
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
