"""
Automated Test Suite for Phase 15: Redis & Celery Background Task Architecture.
Tests configuration, serializers, task definitions, retry policies, reminder pipelines,
cleanup jobs, Google Calendar sync, and safe async task dispatching.
"""

import sys
import os
import time
from datetime import date, datetime, timedelta, timezone

# Add backend directory to sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.config import settings  # type: ignore
from app.database import SessionLocal  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.doctor import Doctor  # type: ignore
from app.models.appointment import Appointment, AppointmentStatus  # type: ignore
from app.models.notification import Notification  # type: ignore
from app.models.prescription import Prescription, Medication  # type: ignore

from app.tasks import (  # type: ignore
    celery_app,
    ping_test_task,
    health_check_task,
    send_email_task,
    send_appointment_confirmation_email_task,
    send_leave_cancellation_email_task,
    send_consultation_summary_email_task,
    send_appointment_reminder_task,
    schedule_appointment_reminders_batch_task,
    send_medication_reminder_task,
    schedule_medication_reminders_batch_task,
    cleanup_expired_slot_holds_task,
    sync_google_calendar_event_task,
    cancel_google_calendar_event_task,
    generate_ical_content,
    dispatch_async_task,
)


def run_phase15_celery_redis_tests():
    print("=======================================================================")
    print(" RUNNING PHASE 15: CELERY & REDIS BACKGROUND TASK ARCHITECTURE TESTS   ")
    print("=======================================================================")

    ts = int(time.time())
    db = SessionLocal()

    try:
        # -------------------------------------------------------------
        # TEST 1: Celery Configuration & Redis URL Mapping
        # -------------------------------------------------------------
        print("\n[TEST 1] Verifying Celery Configuration, Redis URL & Serializers...")
        assert settings.REDIS_URL is not None, "REDIS_URL not configured in settings!"
        assert "redis://" in settings.REDIS_URL or "rediss://" in settings.REDIS_URL, f"Invalid REDIS_URL: {settings.REDIS_URL}"
        assert celery_app.conf.task_serializer == "json", f"Expected json task_serializer, got {celery_app.conf.task_serializer}"
        assert celery_app.conf.result_serializer == "json", f"Expected json result_serializer, got {celery_app.conf.result_serializer}"
        assert celery_app.conf.timezone == "UTC", f"Expected UTC timezone, got {celery_app.conf.timezone}"
        assert celery_app.conf.enable_utc is True
        print(f"-> PASSED: Celery configured with broker '{settings.CELERY_BROKER_URL}' and JSON serializers.")

        # -------------------------------------------------------------
        # TEST 2: Ping & Health Check Tasks Execution
        # -------------------------------------------------------------
        print("\n[TEST 2] Verifying Ping & Health Diagnostic Tasks...")
        ping_res = ping_test_task(message="Diagnostic ping test")
        assert ping_res["status"] == "SUCCESS"
        assert ping_res["message"] == "Diagnostic ping test"

        health_res = health_check_task()
        assert health_res["status"] == "HEALTHY"
        print("-> PASSED: ping_test_task and health_check_task executed successfully.")

        # -------------------------------------------------------------
        # TEST 3: Email Notification Tasks & Retry Policies
        # -------------------------------------------------------------
        print("\n[TEST 3] Verifying Email Notification Tasks & Retry Policies...")
        # Check retry configuration on tasks
        assert send_email_task.max_retries == 3, f"Expected 3 retries, got {send_email_task.max_retries}"
        assert send_appointment_confirmation_email_task.max_retries == 3
        assert send_leave_cancellation_email_task.max_retries == 3
        assert send_consultation_summary_email_task.max_retries == 3

        # Execute direct tasks
        email_res = send_email_task(
            recipient="patient@example.com",
            subject="CareSync Notification",
            body="Your healthcare report is available.",
            template_type="NOTIFICATION"
        )
        assert email_res["status"] == "SENT"
        assert email_res["recipient"] == "patient@example.com"

        leave_res = send_leave_cancellation_email_task(
            appointment_id=101,
            patient_email="patient@example.com",
            patient_name="Alex Brown",
            doctor_name="Dr. Gregory House",
            appointment_date="2026-09-10",
            start_time="11:00",
            reason="Physician leave"
        )
        assert leave_res["status"] == "SENT"
        assert "Doctor unavailable" in leave_res["subject"] or "Appointment Update" in leave_res["subject"]

        summary_res = send_consultation_summary_email_task(
            appointment_id=101,
            patient_email="patient@example.com",
            patient_name="Alex Brown",
            doctor_name="Dr. Gregory House",
            summary_text="Rest, drink electrolytes, take prescribed medications."
        )
        assert summary_res["status"] == "SENT"
        print("-> PASSED: Email notification tasks and retry policies verified.")

        # -------------------------------------------------------------
        # TEST 4: Seed Database Entities for Background Tasks
        # -------------------------------------------------------------
        print("\n[TEST 4] Provisioning Test Entities for Background Execution...")
        pat_user = User(
            name=f"Celery Patient {ts}",
            email=f"celery_pat_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.PATIENT,
            is_active=True
        )
        db.add(pat_user)
        db.flush()

        doc_user = User(
            name=f"Celery Doctor {ts}",
            email=f"celery_doc_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.DOCTOR,
            is_active=True
        )
        db.add(doc_user)
        db.flush()

        doctor = Doctor(
            user_id=doc_user.id,
            specialization="Pulmonology",
            experience=12,
            slot_duration=30,
            is_active=True
        )
        db.add(doctor)
        db.flush()

        target_day = date.today() + timedelta(days=1)
        confirmed_app = Appointment(
            patient_id=pat_user.id,
            doctor_id=doctor.id,
            appointment_date=target_day,
            start_time=datetime.strptime("09:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("09:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Mild persistent dry cough."
        )
        db.add(confirmed_app)

        # Stale hold appointment
        past_hold = datetime.now(timezone.utc) - timedelta(minutes=10)
        expired_hold = Appointment(
            patient_id=pat_user.id,
            doctor_id=doctor.id,
            appointment_date=target_day,
            start_time=datetime.strptime("11:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("11:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.HOLD,
            hold_until=past_hold
        )
        db.add(expired_hold)
        db.commit()
        db.refresh(confirmed_app)
        db.refresh(expired_hold)
        print(f"-> PASSED: Created test records (Patient #{pat_user.id}, Doctor #{doctor.id}, Appointments #{confirmed_app.id}, #{expired_hold.id}).")

        # -------------------------------------------------------------
        # TEST 5: Appointment & Medication Reminder Pipelines
        # -------------------------------------------------------------
        print("\n[TEST 5] Testing Appointment & Medication Reminder Pipelines...")
        # 1. Appointment Confirmation Email Task with Real Entity
        conf_email_res = send_appointment_confirmation_email_task(appointment_id=confirmed_app.id)
        assert conf_email_res["status"] == "SENT"
        assert conf_email_res["recipient"] == pat_user.email

        # 2. Appointment Reminder Task
        rem_res = send_appointment_reminder_task(appointment_id=confirmed_app.id)
        assert rem_res["status"] == "SENT"
        assert rem_res["patient_id"] == pat_user.id

        # 3. Batch Appointment Reminders Task
        batch_rem_res = schedule_appointment_reminders_batch_task(hours_ahead=48)
        assert batch_rem_res["status"] == "COMPLETED"

        # 4. Prescription & Medication Reminders
        rx = Prescription(
            appointment_id=confirmed_app.id,
            doctor_id=doctor.id,
            patient_id=pat_user.id,
            notes="Acute bronchitis therapy",
            follow_up_instructions="Review in 1 week if cough persists."
        )
        db.add(rx)
        db.flush()

        med = Medication(
            prescription_id=rx.id,
            medication_name="Salbutamol Inhaler 100mcg",
            dosage="2 puffs",
            frequency="Every 6 hours as needed",
            duration="5 days",
            instructions="Inhale deeply and rinse mouth.",
            reminder_enabled=True
        )
        db.add(med)
        db.commit()
        db.refresh(med)

        med_rem_res = send_medication_reminder_task(medication_id=med.id, patient_id=pat_user.id)
        assert med_rem_res["status"] == "SENT"
        assert med_rem_res["medication_name"] == "Salbutamol Inhaler 100mcg"

        batch_med_res = schedule_medication_reminders_batch_task()
        assert batch_med_res["status"] == "COMPLETED"
        assert batch_med_res["reminders_sent_count"] >= 1
        print("-> PASSED: Reminder pipelines (single & batch) executed with notification creation.")

        # -------------------------------------------------------------
        # TEST 6: Expired Slot Hold Cleanup Task
        # -------------------------------------------------------------
        print("\n[TEST 6] Testing Expired Slot Hold Cleanup Background Task...")
        assert expired_hold.status == AppointmentStatus.HOLD
        cleanup_res = cleanup_expired_slot_holds_task()
        assert cleanup_res["status"] == "COMPLETED"
        assert cleanup_res["cleaned_count"] >= 1

        db.refresh(expired_hold)
        assert expired_hold.status == AppointmentStatus.EXPIRED
        print(f"-> PASSED: cleanup_expired_slot_holds_task transitioned hold #{expired_hold.id} to EXPIRED.")

        # -------------------------------------------------------------
        # TEST 7: Google Calendar / iCal Event Sync & Cancellation
        # -------------------------------------------------------------
        print("\n[TEST 7] Testing Google Calendar Event Sync & Cancellation Tasks...")
        # Sync Calendar Event
        sync_cal_res = sync_google_calendar_event_task(appointment_id=confirmed_app.id)
        assert sync_cal_res["status"] == "SYNCED"
        assert sync_cal_res["appointment_id"] == confirmed_app.id

        # Cancel Calendar Event
        cancel_cal_res = cancel_google_calendar_event_task(
            appointment_id=confirmed_app.id,
            calendar_event_id="gcal-event-12345",
            cancellation_reason="Patient requested reschedule"
        )
        assert cancel_cal_res["status"] == "CANCELLED"
        assert cancel_cal_res["calendar_event_id"] == "gcal-event-12345"

        # Verify iCal RFC 5545 format
        ical_data = generate_ical_content(confirmed_app)
        assert "BEGIN:VCALENDAR" in ical_data
        assert "VERSION:2.0" in ical_data
        print("-> PASSED: Google Calendar sync and cancellation background tasks verified.")

        # -------------------------------------------------------------
        # TEST 8: Safe Asynchronous Task Dispatcher Resilience
        # -------------------------------------------------------------
        print("\n[TEST 8] Testing Safe Async Task Dispatcher Resilience...")
        # Dispatch with Celery task
        dispatched_ping = dispatch_async_task(ping_test_task, message="Safe Dispatch Ping")
        assert dispatched_ping is not None

        # Dispatch with direct callable
        def dummy_callable(x, y):
            return x + y

        dispatched_math = dispatch_async_task(dummy_callable, 10, 20)
        assert dispatched_math == 30
        print("-> PASSED: dispatch_async_task operates safely and non-blockingly.")

        print("\n=======================================================================")
        print(" ALL 8 PHASE 15 CELERY & REDIS ARCHITECTURE TESTS PASSED!              ")
        print("=======================================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_phase15_celery_redis_tests()
