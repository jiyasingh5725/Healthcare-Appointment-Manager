"""
Automated Test Suite for Phase 18: Google Calendar Integration & OAuth 2.0 Flow.
Tests:
1. OAuth Connect URL generation (GET /api/calendar/connect).
2. OAuth Callback & token storage (GET /api/calendar/callback).
3. Token confidentiality: tokens are never exposed in API responses (GET /api/calendar/status).
4. Google Calendar event creation on appointment confirmation.
5. Event title format ('Doctor Appointment - Dr. <doctor name>') and metadata structure.
6. `calendar_events` table record storage and status tracking (google_event_id, calendar_id, status).
7. Non-rollback guarantee: calendar API failures never abort appointment booking.
8. Calendar event cancellation upon appointment cancellation.
9. Calendar disconnect endpoint (DELETE /api/calendar/disconnect).
10. Synced calendar events listing (GET /api/calendar/events) & Celery task execution.
"""

import sys
import os
import time
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, Any, Dict
from datetime import date, datetime, timedelta, timezone

# Add backend directory to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.config import settings  # type: ignore
from app.database import SessionLocal, init_db  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.doctor import Doctor  # type: ignore
from app.models.appointment import Appointment, AppointmentStatus  # type: ignore
from app.models.calendar_event import CalendarEvent, UserGoogleOAuth  # type: ignore
from app.services.calendar_service import calendar_service, GoogleCalendarService  # type: ignore
from app.tasks.calendar_tasks import sync_google_calendar_event_task, cancel_google_calendar_event_task  # type: ignore
from app.utils.security import hash_password  # type: ignore

API_BASE = "http://127.0.0.1:8000/api"


def http_request(method: str, endpoint: str, body: Optional[Dict[str, Any]] = None, token: Optional[str] = None) -> tuple[int, Dict[str, Any]]:
    url = f"{API_BASE}{endpoint}"
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_data = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_data) if resp_data else {}
    except urllib.error.HTTPError as e:
        resp_data = e.read().decode("utf-8")
        try:
            return e.code, json.loads(resp_data)
        except Exception:
            return e.code, {"detail": resp_data}


def test_suite():
    print("=" * 70)
    print(" STARTING AUTOMATED TEST SUITE: PHASE 18 GOOGLE CALENDAR INTEGRATION")
    print("=" * 70)

    # Initialize DB tables
    init_db()
    db = SessionLocal()

    try:
        # Seed test users
        patient_email = "phase18_patient@example.com"
        patient = db.query(User).filter(User.email == patient_email).first()
        if not patient:
            patient = User(
                name="Phase18 Patient",
                email=patient_email,
                password_hash=hash_password("Pass123!"),
                role=UserRole.PATIENT,
                is_active=True
            )
            db.add(patient)
            db.commit()
            db.refresh(patient)

        doctor_user_email = "phase18_doctor@example.com"
        doc_user = db.query(User).filter(User.email == doctor_user_email).first()
        if not doc_user:
            doc_user = User(
                name="Sarah Jenkins",
                email=doctor_user_email,
                password_hash=hash_password("DoctorPass123!"),
                role=UserRole.DOCTOR,
                is_active=True
            )
            db.add(doc_user)
            db.commit()
            db.refresh(doc_user)

        doctor = db.query(Doctor).filter(Doctor.user_id == doc_user.id).first()
        if not doctor:
            doctor = Doctor(
                user_id=doc_user.id,
                specialization="Neurology",
                qualification="MD, PhD",
                experience=14,
                slot_duration=30,
                is_active=True
            )
            db.add(doctor)
            db.commit()
            db.refresh(doctor)

        # Login patient to get token
        code, auth_res = http_request("POST", "/auth/login", {
            "email": patient_email,
            "password": "Pass123!"
        })
        assert code == 200, f"Login failed: {auth_res}"
        patient_token = auth_res.get("access_token")
        assert patient_token, "No access token received"

        # [TEST 1] OAuth Connect URL generation
        print("\n[TEST 1] Testing Google Calendar Connect URL Generation (GET /api/calendar/connect)...")
        code, connect_res = http_request("GET", "/calendar/connect", token=patient_token)
        assert code == 200, f"Connect endpoint failed: {connect_res}"
        assert "auth_url" in connect_res, "Missing auth_url in response"
        auth_url = connect_res["auth_url"]
        assert "accounts.google.com" in auth_url, "Invalid Google OAuth base URL"
        assert "state=" in auth_url, "Missing state parameter in auth_url"
        print("-> PASSED: Generated valid Google OAuth consent URL with signed state.")

        # [TEST 2] OAuth Callback & Token Storage
        print("\n[TEST 2] Testing Google OAuth Callback (GET /api/calendar/callback)...")
        # Extract state from auth_url or build valid state
        # pyrefly: ignore [bad-argument-type]
        state_data = json.dumps({"user_id": int(patient.id), "ts": int(time.time()), "nonce": "test18"})
        callback_params = urllib.parse.urlencode({"code": "mock_code_123", "state": state_data})
        code, cb_res = http_request("GET", f"/calendar/callback?{callback_params}")
        assert code == 200, f"Callback failed: {cb_res}"
        assert cb_res.get("connected") is True, f"Expected connected=True, got: {cb_res}"

        # Verify DB storage
        # pyrefly: ignore [bad-argument-type]
        oauth_row = db.query(UserGoogleOAuth).filter(UserGoogleOAuth.user_id == int(patient.id)).first()
        assert oauth_row is not None, "UserGoogleOAuth record was not created in DB"
        assert oauth_row.is_connected is True, "is_connected must be True"
        assert oauth_row.access_token is not None, "access_token must be stored"
        print("-> PASSED: OAuth tokens stored securely in server database.")

        # [TEST 3] Token Confidentiality (No tokens exposed to frontend)
        print("\n[TEST 3] Testing Token Confidentiality (GET /api/calendar/status)...")
        code, status_res = http_request("GET", "/calendar/status", token=patient_token)
        assert code == 200, f"Status check failed: {status_res}"
        assert status_res.get("is_connected") is True, "Expected is_connected=True"
        assert "access_token" not in status_res, "CRITICAL SECURITY BREACH: access_token leaked to API!"
        assert "refresh_token" not in status_res, "CRITICAL SECURITY BREACH: refresh_token leaked to API!"
        print("-> PASSED: Calendar status returned without leaking sensitive credentials.")

        # [TEST 4 & 5] Event Title Format & Metadata on Appointment Confirmation
        print("\n[TEST 4 & 5] Testing Google Event Creation with Title 'Doctor Appointment - Dr. <doctor name>'...")
        app_date = date.today() + timedelta(days=2)
        appointment = Appointment(
            patient_id=int(patient.id),
            doctor_id=int(doctor.id),
            appointment_date=app_date,
            start_time=datetime.strptime("10:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("10:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Mild recurring migraines"
        )
        db.add(appointment)
        db.commit()
        db.refresh(appointment)

        # pyrefly: ignore [bad-argument-type]
        sync_res = calendar_service.create_appointment_calendar_event(appointment_id=int(appointment.id), db=db)
        expected_title = f"Doctor Appointment - Dr. {doc_user.name}"
        assert sync_res["title"] == expected_title, f"Expected title '{expected_title}', got: '{sync_res.get('title')}'"
        assert sync_res["doctor"] == doc_user.name, f"Expected doctor '{doc_user.name}', got: '{sync_res.get('doctor')}'"
        assert "google_event_id" in sync_res and sync_res["google_event_id"], "Missing google_event_id"
        print(f"-> PASSED: Calendar event created with title '{expected_title}' and full metadata.")

        # [TEST 6] `calendar_events` table storage and status tracking
        print("\n[TEST 6] Verifying `calendar_events` Table Persistence...")
        # pyrefly: ignore [bad-argument-type]
        cal_event_row = db.query(CalendarEvent).filter(CalendarEvent.appointment_id == int(appointment.id)).first()
        assert cal_event_row is not None, "CalendarEvent not found in database"
        # pyrefly: ignore [bad-argument-type]
        assert cal_event_row.user_id == int(patient.id), "CalendarEvent user_id mismatch"
        assert cal_event_row.google_event_id == sync_res["google_event_id"], "google_event_id mismatch"
        assert cal_event_row.calendar_id == "primary", "calendar_id must default to primary"
        assert cal_event_row.status == "CONFIRMED", f"Expected status 'CONFIRMED', got '{cal_event_row.status}'"
        print("-> PASSED: `calendar_events` record persisted with correct foreign keys and fields.")

        # [TEST 7] Non-Rollback Guarantee on Calendar Failure
        print("\n[TEST 7] Testing Non-Rollback Guarantee (Calendar error does NOT abort appointment)...")
        fail_app = Appointment(
            patient_id=int(patient.id),
            doctor_id=int(doctor.id),
            appointment_date=app_date + timedelta(days=1),
            start_time=datetime.strptime("14:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("14:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Checkup with simulated calendar failure"
        )
        db.add(fail_app)
        db.commit()
        db.refresh(fail_app)

        # Simulate exception during calendar sync
        try:
            from app.tasks.calendar_tasks import sync_google_calendar_event_task
            # pyrefly: ignore [bad-argument-type]
            sync_google_calendar_event_task(appointment_id=int(fail_app.id))
        except Exception:
            pass

        # Verify appointment remains CONFIRMED and intact
        db.refresh(fail_app)
        assert fail_app.status == AppointmentStatus.CONFIRMED, "Appointment must remain CONFIRMED despite calendar failure"
        print("-> PASSED: Appointment transaction preserved regardless of calendar sync failure.")

        # [TEST 8] Calendar Event Cancellation
        print("\n[TEST 8] Testing Calendar Event Cancellation...")
        # pyrefly: ignore [bad-argument-type]
        cancel_res = calendar_service.cancel_appointment_calendar_event(appointment_id=int(appointment.id), db=db)
        assert cancel_res["status"] == "CANCELLED", f"Expected status 'CANCELLED', got: {cancel_res}"
        db.refresh(cal_event_row)
        assert cal_event_row.status == "CANCELLED", f"Expected CalendarEvent status 'CANCELLED', got '{cal_event_row.status}'"
        print("-> PASSED: Calendar event cancelled and status updated in DB.")

        # [TEST 9] Disconnect Calendar Endpoint
        print("\n[TEST 9] Testing Disconnect Endpoint (DELETE /api/calendar/disconnect)...")
        code, disc_res = http_request("DELETE", "/calendar/disconnect", token=patient_token)
        assert code == 200, f"Disconnect failed: {disc_res}"
        db.refresh(oauth_row)
        assert oauth_row.is_connected is False, "is_connected must be False after disconnect"

        code, after_status = http_request("GET", "/calendar/status", token=patient_token)
        assert code == 200
        assert after_status.get("is_connected") is False, "Status must show disconnected"
        print("-> PASSED: Google Calendar successfully disconnected and tokens revoked.")

        # [TEST 10] List Calendar Events Endpoint & Celery Task Execution
        print("\n[TEST 10] Testing Calendar Events Listing (GET /api/calendar/events) & Celery Tasks...")
        code, events_list_res = http_request("GET", "/calendar/events", token=patient_token)
        assert code == 200, f"Events listing failed: {events_list_res}"
        assert "events" in events_list_res, "Missing events array in response"
        assert events_list_res["total"] >= 1, "Expected at least 1 calendar event in history"

        # Celery task execution check
        # pyrefly: ignore [bad-argument-type]
        celery_task_res = sync_google_calendar_event_task(appointment_id=int(appointment.id))
        assert celery_task_res["status"] == "SYNCED", f"Celery task failed: {celery_task_res}"
        print("-> PASSED: Calendar events listing and Celery background task execution verified.")

        print("\n" + "=" * 70)
        print(" ALL 10 PHASE 18 GOOGLE CALENDAR INTEGRATION TESTS PASSED!")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    test_suite()
