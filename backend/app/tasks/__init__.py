"""Background tasks package for Celery."""

import logging
import socket
import urllib.parse
from typing import Any, Callable

from app.config import settings

logger = logging.getLogger(__name__)

from app.tasks.celery_app import celery_app, ping_test_task, health_check_task
from app.tasks.email_tasks import (
    send_email_task,
    send_notification_email_task,
    send_appointment_confirmation_email_task,
    send_booking_confirmation_notifications_task,
    send_appointment_cancellation_email_task,
    send_appointment_cancellation_notifications_task,
    send_leave_cancellation_email_task,
    send_appointment_reschedule_email_task,
    send_consultation_summary_email_task,
)
from app.tasks.reminder_tasks import (
    send_appointment_reminder_task,
    batch_send_appointment_reminders_task,
    send_medication_reminder_task,
    batch_medication_reminders_task,
    schedule_appointment_reminders_batch_task,
    schedule_medication_reminders_batch_task,
)
from app.tasks.cleanup_tasks import (
    cleanup_expired_holds_task,
    cleanup_expired_slot_holds_task,
    cleanup_stale_notifications_task,
)
from app.tasks.calendar_tasks import (
    sync_appointment_to_calendar_task,
    sync_google_calendar_event_task,
    cancel_calendar_event_task,
    cancel_google_calendar_event_task,
    generate_ical_content,
)


def is_redis_available(timeout_sec: float = 0.3) -> bool:
    """
    Fast, non-blocking check to verify if the Celery Redis broker is reachable.
    """
    try:
        parsed = urllib.parse.urlparse(settings.CELERY_BROKER_URL)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except Exception:
        return False


def dispatch_async_task(task_func: Any, *args: Any, **kwargs: Any) -> Any:
    """
    Safe asynchronous task dispatcher:
    Checks if Redis broker is online. If online, enqueues asynchronously with Celery.
    If offline or raises an error, gracefully executes synchronously without crashing or blocking.
    """
    if hasattr(task_func, "apply_async") and is_redis_available(0.3):
        try:
            return task_func.apply_async(args=args, kwargs=kwargs, retry=False)
        except Exception as exc:
            logger.warning(
                f"[Celery:Dispatcher] Async dispatch failed ({exc}). Executing synchronously."
            )
            return task_func(*args, **kwargs)
    elif hasattr(task_func, "delay") and is_redis_available(0.3):
        try:
            return task_func.delay(*args, **kwargs)
        except Exception as exc:
            logger.warning(
                f"[Celery:Dispatcher] Async delay failed ({exc}). Executing synchronously."
            )
            return task_func(*args, **kwargs)
    else:
        logger.info(
            f"[Celery:Dispatcher] Broker offline or direct callable provided. Executing '{getattr(task_func, '__name__', str(task_func))}' synchronously."
        )
        try:
            return task_func(*args, **kwargs)
        except Exception as err:
            logger.error(f"[Celery:Dispatcher] Synchronous execution failed: {err}")
            return None


__all__ = [
    "celery_app",
    "ping_test_task",
    "health_check_task",
    "send_email_task",
    "send_notification_email_task",
    "send_appointment_confirmation_email_task",
    "send_booking_confirmation_notifications_task",
    "send_appointment_cancellation_email_task",
    "send_appointment_cancellation_notifications_task",
    "send_leave_cancellation_email_task",
    "send_appointment_reschedule_email_task",
    "send_consultation_summary_email_task",
    "send_appointment_reminder_task",
    "batch_send_appointment_reminders_task",
    "send_medication_reminder_task",
    "batch_medication_reminders_task",
    "schedule_appointment_reminders_batch_task",
    "schedule_medication_reminders_batch_task",
    "cleanup_expired_holds_task",
    "cleanup_expired_slot_holds_task",
    "cleanup_stale_notifications_task",
    "sync_appointment_to_calendar_task",
    "sync_google_calendar_event_task",
    "cancel_calendar_event_task",
    "cancel_google_calendar_event_task",
    "generate_ical_content",
    "dispatch_async_task",
]
