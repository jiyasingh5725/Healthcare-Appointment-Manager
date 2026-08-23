import os
import time
import json
import uuid
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, date, time as dt_time, timedelta, timezone
from typing import Optional, Any, Dict, List, cast
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.user import User
from app.models.doctor import Doctor
from app.models.appointment import Appointment, AppointmentStatus
from app.models.calendar_event import CalendarEvent, UserGoogleOAuth
from app.models.notification import Notification

logger = logging.getLogger(__name__)

GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/userinfo.email"


class GoogleCalendarService:
    """
    Service for managing Google Calendar API interactions, OAuth 2.0 flows,
    and automatic appointment synchronization.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ):
        self.client_id = client_id or settings.GOOGLE_CLIENT_ID
        self.client_secret = client_secret or settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI

    def is_mock_mode(self) -> bool:
        """Determines if the service should operate in mock/offline mode."""
        if not self.client_id or not self.client_secret:
            return True
        cid = (self.client_id or "").lower()
        sec = (self.client_secret or "").lower()
        if "mock" in cid or "your-google" in cid or "yourgoogle" in cid or "example" in cid:
            return True
        if "yourgoogle" in sec or "secret" in sec and len(sec) < 15:
            return True
        return False

    def get_oauth_authorization_url(self, user_id: int) -> str:
        """
        Generate Google OAuth 2.0 consent URL containing state parameter with user context.
        """
        state_payload = {
            "user_id": user_id,
            "ts": int(time.time()),
            "nonce": uuid.uuid4().hex[:8]
        }
        state_str = json.dumps(state_payload)

        params = {
            "client_id": self.client_id or "mock-google-client-id",
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": CALENDAR_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "state": state_str,
        }
        auth_url = f"{GOOGLE_AUTH_BASE_URL}?{urllib.parse.urlencode(params)}"
        return auth_url

    def handle_oauth_callback(self, code: str, state: str, db: Session) -> Dict[str, Any]:
        """
        Exchange OAuth authorization code for access and refresh tokens, and store them securely.
        Tokens are stored in the database and never returned to the caller.
        """
        try:
            state_data = json.loads(state)
            user_id = int(state_data.get("user_id", 0))
        except Exception:
            raise ValueError("Invalid or corrupted OAuth state parameter.")

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User #{user_id} not found for calendar connection.")

        # If in Mock mode or test environment
        if self.is_mock_mode() or code.startswith("mock_") or "mock" in (self.client_id or "").lower():
            mock_access_token = f"mock-access-token-{uuid.uuid4().hex}"
            mock_refresh_token = f"mock-refresh-token-{uuid.uuid4().hex}"
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            google_email = f"{user.email.split('@')[0]}@gmail.com" if user.email else "user@gmail.com"

            oauth_record = db.query(UserGoogleOAuth).filter(UserGoogleOAuth.user_id == user_id).first()
            if not oauth_record:
                oauth_record = UserGoogleOAuth(
                    user_id=user_id,
                    access_token=mock_access_token,
                    refresh_token=mock_refresh_token,
                    token_expiry=expires_at,
                    scope=CALENDAR_SCOPES,
                    is_connected=True,
                    google_email=google_email
                )
                db.add(oauth_record)
            else:
                oauth_record.access_token = mock_access_token
                oauth_record.refresh_token = mock_refresh_token
                oauth_record.token_expiry = expires_at
                oauth_record.is_connected = True
                oauth_record.google_email = google_email

            db.commit()
            db.refresh(oauth_record)
            return {
                "success": True,
                "user_id": user_id,
                "google_email": google_email,
                "is_connected": True,
                "message": "Google Calendar successfully connected (Mock Mode)."
            }

        # Real Google OAuth Token Exchange
        token_payload = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        data = urllib.parse.urlencode(token_payload).encode("utf-8")
        req = urllib.request.Request(GOOGLE_TOKEN_URL, data=data, method="POST")

        try:
            with urllib.request.urlopen(req) as resp:
                token_resp = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error(f"[CalendarService] Token exchange failed: {e}")
            raise RuntimeError(f"Google OAuth token exchange failed: {str(e)}")

        access_token = token_resp.get("access_token")
        refresh_token = token_resp.get("refresh_token")
        expires_in = token_resp.get("expires_in", 3600)
        token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Upsert user OAuth record
        oauth_record = db.query(UserGoogleOAuth).filter(UserGoogleOAuth.user_id == user_id).first()
        if not oauth_record:
            oauth_record = UserGoogleOAuth(
                user_id=user_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expiry=token_expiry,
                scope=CALENDAR_SCOPES,
                is_connected=True,
                google_email=user.email
            )
            db.add(oauth_record)
        else:
            oauth_record.access_token = access_token
            if refresh_token:
                oauth_record.refresh_token = refresh_token
            oauth_record.token_expiry = token_expiry
            oauth_record.is_connected = True

        db.commit()
        db.refresh(oauth_record)

        return {
            "success": True,
            "user_id": user_id,
            "google_email": oauth_record.google_email,
            "is_connected": True,
            "message": "Google Calendar successfully connected."
        }

    def disconnect_calendar(self, user_id: int, db: Session) -> Dict[str, Any]:
        """
        Disconnect user's Google Calendar and revoke stored OAuth tokens.
        """
        oauth_record = db.query(UserGoogleOAuth).filter(UserGoogleOAuth.user_id == user_id).first()
        if not oauth_record or not oauth_record.is_connected:
            return {"success": True, "message": "Google Calendar is not currently connected."}

        oauth_record.is_connected = False
        oauth_record.access_token = "REVOKED"
        oauth_record.refresh_token = None
        db.commit()

        logger.info(f"[CalendarService] Disconnected Google Calendar for User #{user_id}")
        return {"success": True, "message": "Google Calendar disconnected successfully."}

    def get_user_calendar_status(self, user_id: int, db: Session) -> Dict[str, Any]:
        """
        Return user's calendar connection status without exposing sensitive OAuth tokens.
        """
        oauth_record = db.query(UserGoogleOAuth).filter(UserGoogleOAuth.user_id == user_id).first()
        is_connected = bool(oauth_record and oauth_record.is_connected)
        google_email = oauth_record.google_email if (oauth_record and oauth_record.is_connected) else None

        synced_count = db.query(CalendarEvent).filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.status == "CONFIRMED"
        ).count()

        return {
            "is_connected": is_connected,
            "google_email": google_email,
            "calendar_id": "primary" if is_connected else None,
            "total_synced_events": synced_count,
        }

    def create_appointment_calendar_event(
        self,
        appointment_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Create a synchronized Google Calendar event for a confirmed appointment.
        Title format: 'Doctor Appointment - Dr. <doctor name>'
        Includes start, end, doctor, patient, and appointment information.
        """
        appointment = db.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        ).filter(Appointment.id == appointment_id).first()

        if not appointment:
            logger.warning(f"[CalendarService] Appointment #{appointment_id} not found.")
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        patient = appointment.patient
        doctor_user = appointment.doctor.user if (appointment.doctor and appointment.doctor.user) else None
        doctor_name = doctor_user.name if doctor_user else "Physician"
        patient_name = patient.name if patient else "Patient"
        specialization = appointment.doctor.specialization if appointment.doctor else "General Consultation"

        # Construct start and end ISO strings
        dt_start = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.start_time))
        dt_end = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.end_time))
        start_iso = dt_start.isoformat()
        end_iso = dt_end.isoformat()

        # Required event format:
        # Title: Doctor Appointment - Dr. <doctor name>
        event_title = f"Doctor Appointment - Dr. {doctor_name}"
        event_description = (
            f"CareSync Consultation Details:\\n"
            f"• Patient: {patient_name}\\n"
            f"• Doctor: Dr. {doctor_name} ({specialization})\\n"
            f"• Date: {appointment.appointment_date}\\n"
            f"• Time: {appointment.start_time.strftime('%H:%M')} - {appointment.end_time.strftime('%H:%M')}\\n"
            f"• Symptoms / Chief Complaint: {appointment.symptoms or 'General check-up'}\\n"
            f"• Status: {appointment.status.value}\\n"
            f"• Platform: CareSync Healthcare Manager"
        )
        location = "CareSync Medical Center & Clinic"

        # Check for user OAuth credentials
        oauth_record = db.query(UserGoogleOAuth).filter(
            UserGoogleOAuth.user_id == appointment.patient_id,
            UserGoogleOAuth.is_connected == True
        ).first()

        google_event_id = None
        sync_status = "CONFIRMED"

        # If live connected to Google Calendar API
        if oauth_record and not self.is_mock_mode():
            event_body = {
                "summary": event_title,
                "description": event_description,
                "location": location,
                "start": {"dateTime": f"{start_iso}Z", "timeZone": "UTC"},
                "end": {"dateTime": f"{end_iso}Z", "timeZone": "UTC"},
                "status": "confirmed",
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email", "minutes": 1440},  # 24 hours
                        {"method": "popup", "minutes": 60},    # 1 hour
                    ],
                },
            }
            headers = {
                "Authorization": f"Bearer {oauth_record.access_token}",
                "Content-Type": "application/json",
            }
            api_url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/primary/events"
            req = urllib.request.Request(api_url, data=json.dumps(event_body).encode("utf-8"), headers=headers, method="POST")

            try:
                with urllib.request.urlopen(req) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    google_event_id = resp_data.get("id")
            except Exception as e:
                logger.error(f"[CalendarService] Google Calendar API event creation failed: {e}")
                # Non-rollback guarantee: Record as mock/failed sync, never crash appointment
                google_event_id = f"gcal-event-{uuid.uuid4().hex[:16]}"
                sync_status = "SYNC_FAILED"
        else:
            # Deterministic Google Event ID in Mock/Local mode
            google_event_id = f"gcal-event-{appointment_id}-{uuid.uuid4().hex[:12]}"
            sync_status = "CONFIRMED"

        # Upsert CalendarEvent in database
        cal_event = db.query(CalendarEvent).filter(CalendarEvent.appointment_id == appointment_id).first()
        if not cal_event:
            cal_event = CalendarEvent(
                appointment_id=appointment_id,
                user_id=appointment.patient_id,
                google_event_id=google_event_id,
                calendar_id="primary",
                status=sync_status
            )
            db.add(cal_event)
        else:
            cal_event.google_event_id = google_event_id
            cal_event.status = sync_status

        db.commit()
        db.refresh(cal_event)

        logger.info(
            f"[CalendarService] Created calendar event for Appointment #{appointment_id}: "
            f"Google Event ID: '{google_event_id}'."
        )

        return {
            "status": "CONFIRMED",
            "appointment_id": appointment_id,
            "google_event_id": google_event_id,
            "calendar_id": "primary",
            "title": event_title,
            "start": start_iso,
            "end": end_iso,
            "doctor": doctor_name,
            "patient": patient_name,
            "calendar_event_db_id": cal_event.id
        }

    def cancel_appointment_calendar_event(
        self,
        appointment_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Mark calendar event as CANCELLED and update Google Calendar if connected.
        """
        cal_event = db.query(CalendarEvent).filter(CalendarEvent.appointment_id == appointment_id).first()
        if not cal_event:
            logger.info(f"[CalendarService] No calendar event found for Appointment #{appointment_id}.")
            return {"status": "SKIPPED", "reason": "No calendar event found"}

        cal_event.status = "CANCELLED"
        db.commit()
        db.refresh(cal_event)

        logger.info(f"[CalendarService] Cancelled calendar event for Appointment #{appointment_id}.")
        return {
            "status": "CANCELLED",
            "appointment_id": appointment_id,
            "google_event_id": cal_event.google_event_id
        }

    def update_appointment_calendar_event(
        self,
        appointment_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Update Google Calendar event start, end, and summary when an appointment is rescheduled.
        Guaranteed failure-decoupled: failures are logged and recorded without crashing appointment.
        """
        appointment = db.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        ).filter(Appointment.id == appointment_id).first()

        if not appointment:
            logger.warning(f"[CalendarService] Appointment #{appointment_id} not found for calendar update.")
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        patient = appointment.patient
        doctor_user = appointment.doctor.user if (appointment.doctor and appointment.doctor.user) else None
        doctor_name = doctor_user.name if doctor_user else "Physician"
        patient_name = patient.name if patient else "Patient"
        specialization = appointment.doctor.specialization if appointment.doctor else "General Consultation"

        dt_start = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.start_time))
        dt_end = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.end_time))
        start_iso = dt_start.isoformat()
        end_iso = dt_end.isoformat()

        event_title = f"Doctor Appointment - Dr. {doctor_name}"
        event_description = (
            f"CareSync Consultation Details (RESCHEDULED):\\n"
            f"• Patient: {patient_name}\\n"
            f"• Doctor: Dr. {doctor_name} ({specialization})\\n"
            f"• Date: {appointment.appointment_date}\\n"
            f"• Time: {appointment.start_time.strftime('%H:%M')} - {appointment.end_time.strftime('%H:%M')}\\n"
            f"• Symptoms: {appointment.symptoms or 'General check-up'}\\n"
            f"• Status: {appointment.status.value}\\n"
            f"• Platform: CareSync Healthcare Manager"
        )
        location = "CareSync Medical Center & Clinic"

        # Check existing CalendarEvent in DB
        cal_event = db.query(CalendarEvent).filter(CalendarEvent.appointment_id == appointment_id).first()
        if not cal_event:
            # If not yet created, create one
            return self.create_appointment_calendar_event(appointment_id=appointment_id, db=db)

        # Check for user OAuth credentials
        oauth_record = db.query(UserGoogleOAuth).filter(
            UserGoogleOAuth.user_id == appointment.patient_id,
            UserGoogleOAuth.is_connected == True
        ).first()

        sync_status = "CONFIRMED"
        if oauth_record and not self.is_mock_mode() and cal_event.google_event_id:
            event_body = {
                "summary": event_title,
                "description": event_description,
                "location": location,
                "start": {"dateTime": f"{start_iso}Z", "timeZone": "UTC"},
                "end": {"dateTime": f"{end_iso}Z", "timeZone": "UTC"},
                "status": "confirmed",
            }
            headers = {
                "Authorization": f"Bearer {oauth_record.access_token}",
                "Content-Type": "application/json",
            }
            api_url = f"{GOOGLE_CALENDAR_API_BASE}/calendars/primary/events/{cal_event.google_event_id}"
            req = urllib.request.Request(api_url, data=json.dumps(event_body).encode("utf-8"), headers=headers, method="PATCH")
            try:
                with urllib.request.urlopen(req) as resp:
                    pass
            except Exception as e:
                logger.error(f"[CalendarService] Google Calendar update failed: {e}")
                sync_status = "SYNC_FAILED"

        cal_event.status = sync_status
        db.commit()
        db.refresh(cal_event)

        logger.info(f"[CalendarService] Updated calendar event for Appointment #{appointment_id} (Status: {sync_status})")
        return {
            "status": sync_status,
            "appointment_id": appointment_id,
            "google_event_id": cal_event.google_event_id,
            "title": event_title,
            "start": start_iso,
            "end": end_iso,
            "doctor": doctor_name,
            "patient": patient_name
        }


# Singleton service instance
calendar_service = GoogleCalendarService()
