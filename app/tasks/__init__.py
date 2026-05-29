from celery import Celery

from app.core.config import settings

celery_app = Celery("edms")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
celery_app.autodiscover_tasks(["app.tasks"])

# Import and apply beat schedule
from app.tasks.beat_schedule import CELERY_BEAT_SCHEDULE  # noqa: E402

celery_app.conf.beat_schedule = CELERY_BEAT_SCHEDULE
