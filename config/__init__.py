"""
TeleCRM Backend — config/__init__.py

Load the configured Celery app whenever Django starts.

`celery -A config.celery worker` imports config/celery.py itself, but a Django
process (daphne/gunicorn, a management command, the test runner) never does —
and without it `some_task.delay(...)` binds to Celery's *default* app, which
has none of our settings and points at amqp://localhost. Every enqueue from a
view then fails with a connection error to a broker we do not even run.

This import is what makes `shared_task` in apps/*/tasks.py resolve to the app
configured in config/celery.py, so CELERY_BROKER_URL, the queues and
CELERY_TASK_ALWAYS_EAGER (used by the test suite) all apply.
"""
from config.celery import app as celery_app

__all__ = ("celery_app",)
