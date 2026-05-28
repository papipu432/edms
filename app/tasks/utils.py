"""Utilities for Celery task dispatch with graceful fallback."""

import redis

from app.core.config import settings


def is_celery_available() -> bool:
    """Check if Redis broker is reachable."""
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
        return True
    except Exception:
        return False


def dispatch_task(task, background_tasks, fallback_fn, *args, **kwargs):
    """Dispatch to Celery if available, else use BackgroundTasks as fallback.

    Args:
        task: The Celery task object (has .delay method).
        background_tasks: FastAPI BackgroundTasks instance for fallback.
        fallback_fn: The original async function to run as fallback.
        *args: Positional arguments for the task/fallback function.
        **kwargs: Keyword arguments for the task/fallback function.
    """
    if is_celery_available():
        task.delay(*args, **kwargs)
    else:
        background_tasks.add_task(fallback_fn, *args, **kwargs)
