import logging
from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User, UserRole
from app.utils.dependencies import get_current_user, require_admin
from app.config import settings
from app.tasks.celery_app import celery_app, ping_test_task
from app.tasks.reminder_tasks import (
    batch_send_appointment_reminders_task,
    send_appointment_reminder_task,
    batch_medication_reminders_task,
    send_medication_reminder_task,
)
from app.tasks.cleanup_tasks import (
    cleanup_expired_holds_task,
    cleanup_stale_notifications_task,
)
from app.tasks.calendar_tasks import (
    sync_appointment_to_calendar_task,
    cancel_calendar_event_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Background Tasks"])


@router.get("/health", summary="Celery & Background Workers Health")
def get_tasks_health():
    """
    Retrieve background tasks subsystem configuration and registered task catalog.
    """
    registered_tasks = list(celery_app.tasks.keys())
    return {
        "status": "ONLINE",
        "subsystem": "Celery & Redis Background Worker",
        "broker_url": settings.CELERY_BROKER_URL,
        "backend_url": settings.CELERY_RESULT_BACKEND,
        "timezone": str(celery_app.conf.timezone),
        "task_count": len(registered_tasks),
        "registered_tasks": [t for t in registered_tasks if t.startswith("app.tasks.")],
    }


@router.post("/ping", summary="Trigger Background Ping Test")
def trigger_ping_task(
    message: str = "Diagnostic Ping",
    current_user: User = Depends(get_current_user),
):
    """
    Diagnostic endpoint that triggers ping_test_task.
    """
    try:
        result = ping_test_task(message=message)
        return {
            "success": True,
            "result": result,
            "triggered_by": current_user.email
        }
    except Exception as e:
        logger.error(f"Failed to execute ping task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to trigger ping task: {str(e)}"
        )


@router.post("/reminders/appointments", summary="Trigger Batch Appointment Reminders")
def trigger_appointment_reminders(
    hours_ahead: int = 24,
    current_user: User = Depends(get_current_user),
):
    """
    Trigger batch scan and dispatch for upcoming appointment reminders.
    Available to Admin and Doctor users.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.DOCTOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin or Doctor role required"
        )
    try:
        result = batch_send_appointment_reminders_task(hours_ahead=hours_ahead)
        return {
            "success": True,
            "message": f"Processed {result.get('reminders_sent_count', 0)} appointment reminder(s).",
            "result": result,
            "triggered_by": current_user.email
        }
    except Exception as e:
        logger.error(f"Failed to run batch appointment reminders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run appointment reminders: {str(e)}"
        )


@router.post("/reminders/medications", summary="Trigger Batch Medication Reminders")
def trigger_medication_reminders(
    current_user: User = Depends(get_current_user),
):
    """
    Trigger batch scan and dispatch for active medication dosage reminders.
    Available to Admin and Doctor users.
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.DOCTOR]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Admin or Doctor role required"
        )
    try:
        result = batch_medication_reminders_task()
        return {
            "success": True,
            "message": f"Processed {result.get('reminders_sent_count', 0)} medication reminder(s).",
            "result": result,
            "triggered_by": current_user.email
        }
    except Exception as e:
        logger.error(f"Failed to run batch medication reminders: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run medication reminders: {str(e)}"
        )


@router.post("/cleanup/holds", summary="Trigger Expired Slot Holds Cleanup")
def trigger_cleanup_holds(
    current_user: User = Depends(require_admin),
):
    """
    Trigger cleanup job to release expired appointment slot holds.
    Available to Admin users.
    """
    try:
        result = cleanup_expired_holds_task()
        return {
            "success": True,
            "message": f"Released {result.get('cleaned_count', 0)} expired hold(s).",
            "result": result,
            "triggered_by": current_user.email
        }
    except Exception as e:
        logger.error(f"Failed to run cleanup holds: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run cleanup holds: {str(e)}"
        )
