import logging
from celery import Celery
from celery.schedules import crontab
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Celery App
celery_app = Celery(
    "healthcare_appointment_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.reminder_tasks",
        "app.tasks.cleanup_tasks",
        "app.tasks.calendar_tasks",
    ]
)

# Celery App Configuration & Beat Schedule
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 min hard limit
    task_soft_time_limit=240,  # 4 min soft limit
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=1,
    broker_transport_options={
        "socket_timeout": 1.5,
        "socket_connect_timeout": 1.5,
    },
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Periodic 24-Hour Pre-Appointment Reminder Scan (Runs every 30 minutes)
        "periodic-appointment-reminders-24h": {
            "task": "app.tasks.reminder_tasks.batch_send_appointment_reminders_task",
            "schedule": 1800.0,  # 30 mins
            "args": (24, "24h"),
        },
        # Periodic 1-Hour Pre-Appointment Urgent Reminder Scan (Runs every 15 minutes)
        "periodic-appointment-reminders-1h": {
            "task": "app.tasks.reminder_tasks.batch_send_appointment_reminders_task",
            "schedule": 900.0,  # 15 mins
            "args": (1, "1h"),
        },
        # Periodic Medication Dosage Reminder Scan (Runs every 30 minutes)
        "periodic-medication-reminders-scan": {
            "task": "app.tasks.reminder_tasks.batch_medication_reminders_task",
            "schedule": 1800.0,  # 30 mins
        },
        # Periodic Expired Slot Holds Cleanup (Runs every 5 minutes)
        "periodic-cleanup-expired-holds": {
            "task": "app.tasks.cleanup_tasks.cleanup_expired_holds_task",
            "schedule": 300.0,  # 5 mins
        },
    }
)


@celery_app.task(name="app.tasks.celery_app.ping_test_task", bind=True)
def ping_test_task(self, message: str = "pong") -> dict:
    """
    Basic verification and diagnostic Celery task.
    """
    logger.info(f"[Celery] Ping test task executed with message: {message}")
    return {
        "status": "SUCCESS",
        "task_id": self.request.id,
        "message": message,
        "broker": settings.CELERY_BROKER_URL,
    }


@celery_app.task(name="app.tasks.celery_app.health_check_task", bind=True)
def health_check_task(self) -> dict:
    """
    Celery worker health diagnostic task.
    """
    return {
        "status": "HEALTHY",
        "task_id": self.request.id,
        "broker": settings.CELERY_BROKER_URL,
        "backend": settings.CELERY_RESULT_BACKEND,
    }
