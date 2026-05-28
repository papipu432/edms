"""Utilities for Celery task dispatch with graceful fallback."""

import time

import redis

from app.core.config import settings

_celery_available_cache: tuple[bool, float] | None = None
_CACHE_TTL = 10.0  # seconds


def is_celery_available() -> bool:
    """Check if Redis broker is reachable (cached for 10 seconds)."""
    global _celery_available_cache
    now = time.time()
    if _celery_available_cache and (now - _celery_available_cache[1]) < _CACHE_TTL:
        return _celery_available_cache[0]
    try:
        r = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        r.ping()
        result = True
    except Exception:
        result = False
    _celery_available_cache = (result, now)
    return result


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
