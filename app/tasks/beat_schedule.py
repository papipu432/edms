"""Celery beat schedule configuration."""

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "check-lifecycle-alerts-daily": {
        "task": "app.tasks.lifecycle.check_lifecycle_alerts_task",
        "schedule": crontab(hour=0, minute=0),  # Daily at midnight UTC
    },
    "generate-scheduled-reports": {
        "task": "app.tasks.reports.generate_scheduled_reports_task",
        "schedule": crontab(hour=1, minute=0),  # Daily at 1am UTC
    },
    "generate-daily-note": {
        "task": "app.tasks.daily_notes.generate_daily_note_task",
        "schedule": crontab(hour=6, minute=0),  # Daily at 6am UTC
    },
}
