from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models.notification import Notification, NotificationStatus, NotificationType
from app.models.user import User, UserRole
from app.utils.dependencies import get_current_user, require_role

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", summary="Get User Notifications")
def get_user_notifications(
    unread_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve all notifications for the authenticated user (patient/doctor/admin).
    """
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read == False)

    notifs = query.order_by(Notification.created_at.desc()).all()

    return [
        {
            "id": n.id,
            "appointment_id": n.appointment_id,
            "title": n.title,
            "message": n.message,
            "notification_type": n.notification_type,
            "type": n.notification_type,
            "channel": n.channel,
            "status": n.status,
            "email_job_status": n.status,
            "calendar_job_status": n.calendar_job_status,
            "retry_count": n.retry_count,
            "error_message": n.error_message,
            "is_read": n.is_read,
            "sent_at": n.sent_at.isoformat() if n.sent_at else None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifs
    ]


@router.patch("/{notification_id}/read", summary="Mark Notification as Read")
def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mark a specific notification as read.
    """
    notif = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )

    if not notif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification #{notification_id} not found.",
        )

    notif.is_read = True
    db.commit()
    return {"message": "Notification marked as read", "id": notification_id}


# -----------------------------------------------------------------------------
# Admin Notification Monitoring & Diagnostic Endpoints (Phase 16)
# -----------------------------------------------------------------------------

@router.get("/admin/stats", summary="Admin Notification Delivery Statistics")
def get_admin_notification_stats(
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """
    Aggregated email and notification delivery metrics for system administration.
    """
    total = db.query(func.count(Notification.id)).scalar() or 0
    sent = db.query(func.count(Notification.id)).filter(Notification.status == NotificationStatus.SENT.value).scalar() or 0
    failed = db.query(func.count(Notification.id)).filter(Notification.status == NotificationStatus.FAILED.value).scalar() or 0
    pending = db.query(func.count(Notification.id)).filter(Notification.status == NotificationStatus.PENDING.value).scalar() or 0
    retrying = db.query(func.count(Notification.id)).filter(Notification.status == NotificationStatus.RETRYING.value).scalar() or 0
    total_retries = db.query(func.sum(Notification.retry_count)).scalar() or 0

    success_rate = round((sent / total * 100), 1) if total > 0 else 100.0

    return {
        "status": "ONLINE",
        "provider": settings.EMAIL_PROVIDER,
        "from_email": settings.EMAIL_FROM,
        "total_notifications": total,
        "sent_count": sent,
        "failed_count": failed,
        "pending_count": pending,
        "retrying_count": retrying,
        "total_retries": int(total_retries),
        "success_rate_percentage": success_rate,
    }


@router.get("/admin/logs", summary="Admin Notification Delivery Logs")
def get_admin_notification_logs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (SENT, FAILED, PENDING, RETRYING)"),
    type_filter: Optional[str] = Query(None, alias="type", description="Filter by notification type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """
    System-wide notification and email delivery logs with detailed retry and error tracing.
    """
    query = db.query(Notification).options(joinedload(Notification.user), joinedload(Notification.appointment))

    if status_filter:
        query = query.filter(Notification.status == status_filter.strip().upper())
    if type_filter:
        query = query.filter(Notification.notification_type == type_filter.strip().upper())

    total_count = query.count()
    logs = query.order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "logs": [
            {
                "id": n.id,
                "user_id": n.user_id,
                "recipient_name": n.user.name if n.user else "Unknown",
                "recipient_email": n.user.email if n.user else "N/A",
                "appointment_id": n.appointment_id,
                "notification_type": n.notification_type,
                "channel": n.channel,
                "status": n.status,
                "retry_count": n.retry_count,
                "error_message": n.error_message,
                "title": n.title,
                "message": n.message,
                "sent_at": n.sent_at.isoformat() if n.sent_at else None,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in logs
        ],
    }


@router.post("/admin/retry/{notification_id}", summary="Admin Manual Notification Retry")
def retry_failed_notification(
    notification_id: int,
    current_user: User = Depends(require_role([UserRole.ADMIN])),
    db: Session = Depends(get_db),
):
    """
    Manually trigger re-dispatch of a failed or pending notification.
    """
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail=f"Notification #{notification_id} not found.")

    from app.tasks import dispatch_async_task, send_notification_email_task

    notif.status = NotificationStatus.PENDING.value
    notif.error_message = None
    db.commit()

    dispatch_async_task(send_notification_email_task, notif.id)

    return {
        "success": True,
        "message": f"Notification #{notification_id} queued for retry.",
        "notification_id": notification_id,
    }
