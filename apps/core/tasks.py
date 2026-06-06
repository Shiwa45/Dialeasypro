"""
TeleCRM Backend — apps/core/tasks.py

Base Celery task classes with tenant schema awareness.
All TeleCRM Celery tasks should inherit from TenantAwareTask
when they need to operate within a specific tenant's schema.

Usage:
    from apps.core.tasks import TenantAwareTask

    @shared_task(base=TenantAwareTask, bind=True)
    def my_tenant_task(self, schema_name, *args, **kwargs):
        # self.schema_name is set, connection is already in correct schema
        leads = Lead.objects.filter(status='new')  # queries correct tenant schema
"""
import logging

from celery import Task
from django.db import connection

logger = logging.getLogger(__name__)


class TenantAwareTask(Task):
    """
    Base Celery task that sets the correct tenant schema before executing.

    The first positional argument to any task inheriting this class
    MUST be `schema_name`. The task will automatically switch to that
    schema before running and restore the previous schema after.

    Example task definition:
        @shared_task(base=TenantAwareTask, bind=True)
        def send_reminders(self, schema_name):
            leads = Lead.objects.filter(...)  # runs in schema_name schema
    """

    abstract = True

    def __call__(self, *args, **kwargs):
        """Wrap task execution with schema context."""
        schema_name = args[0] if args else kwargs.get("schema_name", "public")
        self.schema_name = schema_name

        previous_schema = connection.schema_name
        try:
            connection.set_schema(schema_name)
            logger.debug(f"[Task:{self.name}] Switched to schema: {schema_name}")
            return super().__call__(*args, **kwargs)
        except Exception as exc:
            logger.error(
                f"[Task:{self.name}] Failed in schema {schema_name}: {exc}",
                exc_info=True,
            )
            raise
        finally:
            connection.set_schema(previous_schema)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails — log with tenant context."""
        schema_name = args[0] if args else kwargs.get("schema_name", "unknown")
        logger.error(
            f"[Task:{self.name}] FAILED | schema={schema_name} | "
            f"task_id={task_id} | error={exc}",
            exc_info=einfo,
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called on task retry."""
        schema_name = args[0] if args else kwargs.get("schema_name", "unknown")
        logger.warning(
            f"[Task:{self.name}] RETRYING | schema={schema_name} | error={exc}"
        )

    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success."""
        schema_name = args[0] if args else kwargs.get("schema_name", "unknown")
        logger.debug(
            f"[Task:{self.name}] SUCCESS | schema={schema_name} | task_id={task_id}"
        )


class PublicSchemaTask(Task):
    """
    Base Celery task that always runs in the public schema.
    Used for platform-level tasks (trial expiry checks, invoice generation, etc.)
    """

    abstract = True

    def __call__(self, *args, **kwargs):
        previous_schema = connection.schema_name
        try:
            connection.set_schema_to_public()
            return super().__call__(*args, **kwargs)
        finally:
            connection.set_schema(previous_schema)
