"""
Automated Test Suite for Phase 15: Asynchronous Background Tasks, Celery/Redis Workers,
Automated Reminders, Slot Cleanup, and Calendar Synchronization.
"""

import sys
import os
import urllib.request
import urllib.error
import json
import time
from datetime import date, datetime, timedelta, timezone

# Add backend directory to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.doctor import Doctor  # type: ignore
from app.models.appointment import Appointment, AppointmentStatus  # type: ignore
from app.models.notification import Notification  # type: ignore
from app.models.prescription import Prescription, Medication  # type: ignore
from app.tasks.celery_app import celery_app, ping_test_task  # type: ignore
from app.tasks.email_tasks import (  # type: ignore
    send_email_task,
    send_appointment_confirmation_email_task,
    send_leave_cancellation_email_task,
    send_consultation_summary_email_task,
)
from app.tasks.reminder_tasks import (  # type: ignore
    send_appointment_reminder_task,
    batch_send_appointment_reminders_task,
    send_medication_reminder_task,
    batch_medication_reminders_task,
)
from app.tasks.cleanup_tasks import (  # type: ignore
    cleanup_expired_holds_task,
    cleanup_stale_notifications_task,
)
from app.tasks.calendar_tasks import (  # type: ignore
    sync_appointment_to_calendar_task,
    cancel_calendar_event_task,
    generate_ical_content,
)

BASE_URL = "http://127.0.0.1:8000"


def http_request(method, endpoint, body=None, token=None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            content = response.read().decode("utf-8")
            try:
                data = json.loads(content) if content else {}
            except Exception:
                data = content
            return status, data
    except urllib.error.HTTPError as e:
        status = e.code
        content = e.read().decode("utf-8")
        try:
            data = json.loads(content) if content else {}
        except Exception:
            data = {"raw": content}
        return status, data


def run_phase15_tests():
    print("=======================================================================")
    print(" RUNNING PHASE 15: BACKGROUND TASKS, CELERY, REMINDERS & CALENDAR SYNC ")
    print("=======================================================================")

    ts = int(time.time())
    db = SessionLocal()

    try:
        # -------------------------------------------------------------
        # TEST 1: Celery Application Initialization & Ping Test
        # -------------------------------------------------------------
        print("\n[TEST 1] Celery App Initialization & Ping Task...")
        assert celery_app is not None, "Celery app not initialized!"
        registered = list(celery_app.tasks.keys())
        expected_tasks = [
            "app.tasks.celery_app.ping_test_task",
            "app.tasks.email_tasks.send_email_task",
            "app.tasks.email_tasks.send_appointment_confirmation_email_task",
            "app.tasks.email_tasks.send_leave_cancellation_email_task",
            "app.tasks.email_tasks.send_consultation_summary_email_task",
            "app.tasks.reminder_tasks.send_appointment_reminder_task",
            "app.tasks.reminder_tasks.batch_send_appointment_reminders_task",
            "app.tasks.reminder_tasks.send_medication_reminder_task",
            "app.tasks.reminder_tasks.batch_medication_reminders_task",
            "app.tasks.cleanup_tasks.cleanup_expired_holds_task",
            "app.tasks.calendar_tasks.sync_appointment_to_calendar_task",
            "app.tasks.calendar_tasks.cancel_calendar_event_task",
        ]
        for t_name in expected_tasks:
            assert t_name in registered, f"Task {t_name} missing from Celery registry!"
        
        ping_res = ping_test_task(message="Diagnostic ping test")
        assert ping_res["status"] == "SUCCESS", f"Ping failed: {ping_res}"
        assert ping_res["message"] == "Diagnostic ping test"
        print("-> PASSED: Celery app and all 12 tasks registered.")

        # -------------------------------------------------------------
        # TEST 2: Email Background Tasks Execution
        # -------------------------------------------------------------
        print("\n[TEST 2] Testing Email Background Tasks...")
        email_res = send_email_task(
            recipient="test@example.com",
            subject="Welcome to CareSync",
            body="Welcome to the healthcare portal.",
            template_type="WELCOME"
        )
        assert email_res["status"] == "SENT"
        assert email_res["recipient"] == "test@example.com"

        leave_cancel_res = send_leave_cancellation_email_task(
            appointment_id=9999,
            patient_email="patient@example.com",
            patient_name="John Doe",
            doctor_name="Dr. Gregory House",
            appointment_date="2026-09-01",
            start_time="10:00",
            reason="Physician urgent conference"
        )
        assert leave_cancel_res["status"] == "SENT"
        assert leave_cancel_res["subject"].startswith("Appointment Update:")

        summary_email_res = send_consultation_summary_email_task(
            appointment_id=9999,
            patient_email="patient@example.com",
            patient_name="John Doe",
            doctor_name="Dr. Gregory House",
            summary_text="Rest, stay hydrated, take prescribed amoxicillin."
        )
        assert summary_email_res["status"] == "SENT"
        print("-> PASSED: Email delivery tasks executed with proper tracking metadata.")

        # -------------------------------------------------------------
        # TEST 3: User & Doctor Provisioning for Live Workflows
        # -------------------------------------------------------------
        print("\n[TEST 3] Provisioning Test Data for Background Jobs...")
        # Create Test Patient
        patient_user = User(
            name=f"Phase15 Patient {ts}",
            email=f"phase15_pat_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.PATIENT,
            is_active=True
        )
        db.add(patient_user)
        db.flush()

        # Create Test Doctor
        doc_user = User(
            name=f"Phase15 Doctor {ts}",
            email=f"phase15_doc_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.DOCTOR,
            is_active=True
        )
        db.add(doc_user)
        db.flush()

        doctor = Doctor(
            user_id=doc_user.id,
            specialization="Internal Medicine",
            experience=8,
            slot_duration=30,
            is_active=True
        )
        db.add(doctor)
        db.flush()

        # Create Confirmed Appointment for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        confirmed_app = Appointment(
            patient_id=patient_user.id,
            doctor_id=doctor.id,
            appointment_date=tomorrow,
            start_time=datetime.strptime("10:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("10:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Mild seasonal cough and fatigue."
        )
        db.add(confirmed_app)

        # Create Expired Hold Appointment
        past_hold_time = datetime.now(timezone.utc) - timedelta(minutes=15)
        expired_hold_app = Appointment(
            patient_id=patient_user.id,
            doctor_id=doctor.id,
            appointment_date=tomorrow,
            start_time=datetime.strptime("14:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("14:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.HOLD,
            hold_until=past_hold_time
        )
        db.add(expired_hold_app)
        db.commit()
        db.refresh(confirmed_app)
        db.refresh(expired_hold_app)
        print(f"-> PASSED: Test Patient #{patient_user.id}, Doctor #{doctor.id}, and Appointments created.")

        # -------------------------------------------------------------
        # TEST 4: Appointment Reminder Task Execution
        # -------------------------------------------------------------
        print("\n[TEST 4] Testing Single & Batch Appointment Reminders...")
        # Single reminder task
        reminder_res = send_appointment_reminder_task(appointment_id=confirmed_app.id)
        assert reminder_res["status"] == "SENT", f"Reminder failed: {reminder_res}"
        assert reminder_res["patient_id"] == patient_user.id

        # Verify notification created in DB
        notif = db.query(Notification).filter(
            Notification.appointment_id == confirmed_app.id,
            Notification.type == "APPOINTMENT_REMINDER"
        ).first()
        assert notif is not None, "Notification record was not created by reminder task!"
        assert notif.is_read is False
        assert "Upcoming Appointment Reminder" in notif.title

        # Batch reminder task
        batch_res = batch_send_appointment_reminders_task(hours_ahead=48)
        assert batch_res["status"] == "COMPLETED"
        print(f"-> PASSED: Appointment reminders generated notification #{notif.id}.")

        # -------------------------------------------------------------
        # TEST 5: Prescription Medication Reminder Task Execution
        # -------------------------------------------------------------
        print("\n[TEST 5] Testing Medication Dosage Reminders...")
        # Create Prescription with medication having reminder_enabled=True
        rx = Prescription(
            appointment_id=confirmed_app.id,
            doctor_id=doctor.id,
            patient_id=patient_user.id,
            notes="Post-visit medication therapy",
            follow_up_instructions="Drink plenty of fluids."
        )
        db.add(rx)
        db.flush()

        med1 = Medication(
            prescription_id=rx.id,
            medication_name="Azithromycin 500mg",
            dosage="1 tab daily",
            frequency="Once daily before breakfast",
            duration="3 days",
            instructions="Complete all 3 days",
            reminder_enabled=True
        )
        db.add(med1)
        db.commit()
        db.refresh(med1)

        # Single medication reminder task
        med_rem_res = send_medication_reminder_task(medication_id=med1.id)
        assert med_rem_res["status"] == "SENT", f"Med reminder failed: {med_rem_res}"
        assert med_rem_res["medication_name"] == "Azithromycin 500mg"

        # Verify Notification
        med_notif = db.query(Notification).filter(
            Notification.user_id == patient_user.id,
            Notification.type == "MEDICATION_REMINDER"
        ).first()
        assert med_notif is not None, "Medication reminder notification missing in DB!"
        assert "Azithromycin 500mg" in med_notif.message

        # Batch medication reminders
        batch_med_res = batch_medication_reminders_task()
        assert batch_med_res["status"] == "COMPLETED"
        assert batch_med_res["reminders_sent_count"] >= 1
        print("-> PASSED: Medication dosage reminders successfully scheduled and dispatched.")

        # -------------------------------------------------------------
        # TEST 6: Expired Slot Holds Cleanup Task
        # -------------------------------------------------------------
        print("\n[TEST 6] Testing Slot Hold Cleanup Background Task...")
        assert expired_hold_app.status == AppointmentStatus.HOLD
        cleanup_res = cleanup_expired_holds_task()
        assert cleanup_res["status"] == "COMPLETED"
        assert cleanup_res["cleaned_count"] >= 1

        db.refresh(expired_hold_app)
        assert expired_hold_app.status == AppointmentStatus.EXPIRED, f"Expected EXPIRED status, got {expired_hold_app.status}"
        print(f"-> PASSED: Expired slot hold #{expired_hold_app.id} released and transitioned to EXPIRED.")

        # -------------------------------------------------------------
        # TEST 7: Calendar Sync & RFC 5545 iCal Generation
        # -------------------------------------------------------------
        print("\n[TEST 7] Testing Calendar Event (.ics) Sync & Cancellation...")
        # 1. Direct RFC 5545 iCal generator
        ical_str = generate_ical_content(confirmed_app, is_cancellation=False)
        assert "BEGIN:VCALENDAR" in ical_str
        assert "VERSION:2.0" in ical_str
        assert "BEGIN:VEVENT" in ical_str
        assert "SUMMARY:Medical Consultation:" in ical_str
        assert "STATUS:CONFIRMED" in ical_str
        assert "END:VCALENDAR" in ical_str

        # 2. Celery sync task
        sync_res = sync_appointment_to_calendar_task(appointment_id=confirmed_app.id)
        assert sync_res["status"] == "SYNCED"
        assert sync_res["ical_size_bytes"] > 50

        # 3. Cancellation iCal generator
        ical_cancel_str = generate_ical_content(confirmed_app, is_cancellation=True, cancellation_reason="Doctor rescheduled")
        assert "METHOD:CANCEL" in ical_cancel_str
        assert "STATUS:CANCELLED" in ical_cancel_str
        assert "Cancellation Reason: Doctor rescheduled" in ical_cancel_str

        # 4. Celery cancel task
        cancel_res = cancel_calendar_event_task(appointment_id=confirmed_app.id, cancellation_reason="Clinic maintenance")
        assert cancel_res["status"] == "CANCELLED"
        print("-> PASSED: RFC 5545 iCalendar generation and sync tasks verified.")

        # -------------------------------------------------------------
        # TEST 8: Live Tasks API Endpoints & Health Route
        # -------------------------------------------------------------
        print("\n[TEST 8] Testing /api/tasks Health & Diagnostic Endpoints...")
        # Tasks health endpoint (public / diagnostic)
        status, health_data = http_request("GET", "/api/tasks/health")
        assert status == 200, f"Tasks health failed: {health_data}"
        assert isinstance(health_data, dict), f"Expected dict, got {type(health_data)}"
        assert health_data.get("status") == "ONLINE"
        assert int(health_data.get("task_count", 0)) >= 12
        assert "app.tasks.reminder_tasks.send_appointment_reminder_task" in health_data.get("registered_tasks", [])
        print("-> PASSED: /api/tasks/health verified.")

        # Admin login for live task triggers
        admin_login = {
            "email": "test_admin_phase3@example.com",
            "password": "AdminPass123!"
        }
        status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
        assert status == 200, f"Admin login failed: {admin_data}"
        admin_token = admin_data["access_token"]

        # POST /api/tasks/ping
        status, ping_api_res = http_request("POST", "/api/tasks/ping?message=LiveApiPing", token=admin_token)
        assert status == 200, f"Ping API failed: {ping_api_res}"
        assert ping_api_res["success"] is True

        # POST /api/tasks/reminders/appointments
        status, rem_api_res = http_request("POST", "/api/tasks/reminders/appointments?hours_ahead=48", token=admin_token)
        assert status == 200, f"Reminder trigger API failed: {rem_api_res}"
        assert rem_api_res["success"] is True

        # POST /api/tasks/reminders/medications
        status, med_api_res = http_request("POST", "/api/tasks/reminders/medications", token=admin_token)
        assert status == 200, f"Medication trigger API failed: {med_api_res}"
        assert med_api_res["success"] is True

        # POST /api/tasks/cleanup/holds
        status, cleanup_api_res = http_request("POST", "/api/tasks/cleanup/holds", token=admin_token)
        assert status == 200, f"Cleanup API failed: {cleanup_api_res}"
        assert cleanup_api_res["success"] is True
        print("-> PASSED: Live /api/tasks diagnostic and trigger endpoints verified.")

        # -------------------------------------------------------------
        # TEST 9: Calendar Invite (.ics) Download Endpoint with RBAC
        # -------------------------------------------------------------
        print("\n[TEST 9] Testing /api/appointments/{id}/calendar-invite Endpoint...")
        # Download as Admin
        status, ics_res = http_request("GET", f"/api/appointments/{confirmed_app.id}/calendar-invite", token=admin_token)
        assert status == 200, f"Calendar invite download failed: {ics_res}"
        print("-> PASSED: Calendar invite (.ics) downloaded successfully.")

        # -------------------------------------------------------------
        # TEST 10: RBAC Access Control on Task Operations
        # -------------------------------------------------------------
        print("\n[TEST 10] Testing RBAC Security Restrictions on Tasks API...")
        # Patient login
        pat_login_payload = {
            "name": f"RBAC Patient {ts}",
            "email": f"rbac_pat_{ts}@example.com",
            "password": "PatientPass123!",
            "phone": "+15550001111"
        }
        status, pat_reg = http_request("POST", "/api/auth/register", body=pat_login_payload)
        assert status == 201
        _, pat_auth = http_request("POST", "/api/auth/login", body={"email": pat_login_payload["email"], "password": pat_login_payload["password"]})
        patient_token = pat_auth["access_token"]

        # Patient attempting cleanup holds trigger -> Should receive 403 Forbidden
        status, blocked_res = http_request("POST", "/api/tasks/cleanup/holds", token=patient_token)
        assert status == 403, f"Expected 403 Forbidden for patient on cleanup trigger, got {status}: {blocked_res}"

        # Unauthenticated request to /api/tasks/ping -> Should receive 401 Unauthorized
        status, unauth_res = http_request("POST", "/api/tasks/ping")
        assert status == 401, f"Expected 401 Unauthorized, got {status}: {unauth_res}"
        print("-> PASSED: RBAC security enforced on background task triggers.")

        print("\n=======================================================================")
        print(" ALL 10 PHASE 15 BACKGROUND TASKS & CALENDAR SYNC TESTS PASSED!        ")
        print("=======================================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_phase15_tests()
