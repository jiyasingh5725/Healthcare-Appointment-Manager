import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.notification import Notification

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.cleanup_tasks.cleanup_expired_holds_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def cleanup_expired_holds_task(self) -> dict[str, Any]:
    """
    Periodic background job to release expired appointment slot holds.
    Finds all rows in HOLD status where hold_until <= now_utc and transitions them to EXPIRED.
    """
    db = SessionLocal()
    try:
        now_utc = datetime.now(timezone.utc)
        expired_holds = db.query(Appointment).filter(
            Appointment.status == AppointmentStatus.HOLD,
            Appointment.hold_until <= now_utc
        ).all()

        cleaned_count = len(expired_holds)
        cleaned_ids = []
        for app in expired_holds:
            app.status = AppointmentStatus.EXPIRED
            app.updated_at = now_utc
            cleaned_ids.append(app.id)

        db.commit()
        logger.info(f"[Celery:Cleanup] Cleaned {cleaned_count} expired appointment holds.")
        return {
            "status": "COMPLETED",
            "cleaned_count": cleaned_count,
            "appointment_ids": cleaned_ids,
            "timestamp": now_utc.isoformat()
        }
    except Exception as e:
        db.rollback()
        logger.error(f"[Celery:Cleanup] Failed to clean expired holds: {e}")
        raise
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.cleanup_tasks.cleanup_stale_notifications_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2
)
def cleanup_stale_notifications_task(self, days_old: int = 60) -> dict[str, Any]:
    """
    Maintenance task to clean up old read notifications.
    """
    db = SessionLocal()
    try:
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        stale_notifications = db.query(Notification).filter(
            Notification.is_read == True,
            Notification.created_at <= cutoff_date
        ).all()

        deleted_count = len(stale_notifications)
        for n in stale_notifications:
            db.delete(n)

        db.commit()
        logger.info(f"[Celery:Cleanup] Deleted {deleted_count} stale notifications older than {days_old} days.")
        return {
            "status": "COMPLETED",
            "deleted_count": deleted_count,
            "days_old": days_old
        }
    except Exception as e:
        db.rollback()
        logger.error(f"[Celery:Cleanup] Failed to clean stale notifications: {e}")
        raise
    finally:
        db.close()


cleanup_expired_slot_holds_task = cleanup_expired_holds_task

