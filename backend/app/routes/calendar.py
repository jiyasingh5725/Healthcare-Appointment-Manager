import logging
from typing import Optional, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User, UserRole
from app.models.calendar_event import CalendarEvent, UserGoogleOAuth
from app.models.appointment import Appointment
from app.services.calendar_service import calendar_service
from app.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendar", tags=["Google Calendar Integration & OAuth 2.0"])


@router.get(
    "/connect",
    summary="Get Google OAuth 2.0 Authorization URL"
)
def get_google_calendar_connect_url(
    current_user: User = Depends(get_current_user)
):
    """
    Generate Google OAuth 2.0 consent URL for connecting patient or doctor Google Calendar.
    """
    import json, time, uuid
    is_mock = calendar_service.is_mock_mode()
    state_payload = {
        "user_id": int(current_user.id),
        "ts": int(time.time()),
        "nonce": uuid.uuid4().hex[:8]
    }
    state_str = json.dumps(state_payload)
    auth_url = calendar_service.get_oauth_authorization_url(user_id=int(current_user.id))
    return {
        "success": True,
        "auth_url": auth_url,
        "is_mock": is_mock,
        "state": state_str,
        "user_id": int(current_user.id),
        "message": "Direct user to auth_url to complete Google Calendar OAuth consent."
    }


@router.get(
    "/callback",
    summary="Google OAuth 2.0 Authorization Callback"
)
def google_calendar_oauth_callback(
    code: str = Query(..., description="Google OAuth authorization code"),
    state: str = Query(..., description="Encoded state parameter with user context"),
    db: Session = Depends(get_db)
):
    """
    Handles Google OAuth redirect, exchanges code for access & refresh tokens,
    stores credentials securely, and redirects user back to dashboard.
    """
    try:
        res = calendar_service.handle_oauth_callback(code=code, state=state, db=db)
        return {
            "success": True,
            "connected": True,
            "google_email": res.get("google_email"),
            "message": "Google Calendar successfully connected."
        }
    except Exception as e:
        logger.error(f"[CalendarRoute] OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to complete Google Calendar connection: {str(e)}"
        )


@router.delete(
    "/disconnect",
    summary="Disconnect Google Calendar"
)
def disconnect_google_calendar(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Revoke and delete stored Google OAuth tokens for the authenticated user.
    """
    res = calendar_service.disconnect_calendar(user_id=int(current_user.id), db=db)
    return res


@router.get(
    "/status",
    summary="Get Current User's Google Calendar Connection Status"
)
def get_calendar_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve connection status for the logged-in user without exposing OAuth tokens.
    """
    return calendar_service.get_user_calendar_status(user_id=int(current_user.id), db=db)


@router.get(
    "/events",
    summary="List Synced Calendar Events"
)
def list_user_calendar_events(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all synced Google Calendar events for the user's appointments.
    """
    events = db.query(CalendarEvent).options(
        joinedload(CalendarEvent.appointment)
    ).filter(
        CalendarEvent.user_id == current_user.id
    ).order_by(CalendarEvent.created_at.desc()).all()

    return {
        "total": len(events),
        "events": [
            {
                "id": ev.id,
                "appointment_id": ev.appointment_id,
                "google_event_id": ev.google_event_id,
                "calendar_id": ev.calendar_id,
                "status": ev.status,
                "created_at": ev.created_at.isoformat() if ev.created_at else None,
                "updated_at": ev.updated_at.isoformat() if ev.updated_at else None,
            }
            for ev in events
        ]
    }


@router.post(
    "/sync/{appointment_id}",
    summary="Manually Sync Appointment to Google Calendar"
)
def sync_appointment_calendar_manually(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Manually create or synchronize a Google Calendar event for an appointment.
    """
    app = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if app.patient_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Forbidden")

    result = calendar_service.create_appointment_calendar_event(appointment_id=appointment_id, db=db)
    return {"success": True, "result": result}
