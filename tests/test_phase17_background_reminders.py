"""
Automated Test Suite for Phase 17: Background Reminders System & Celery Workers.
Tests:
1. 24-hour and 1-hour pre-appointment reminder generation.
2. Suppression of reminders for CANCELLED and COMPLETED appointments.
3. Idempotent duplicate reminder prevention.
4. Medication frequency parsing (Once daily, Twice daily, Three times daily, Every X hours).
5. Medication next dose time calculation.
6. Exclusion of disabled medication reminders (reminder_enabled=False).
7. Timestamp tracking (scheduled_at, sent_at, status).
8. Batch Celery reminder dispatching jobs.
9. Patient medication & reminder APIs (listing, toggle reminder status, upcoming schedules).
10. Patient diagnostic reminder trigger endpoint.
"""

import sys
import os
import time
import json
import urllib.request
import urllib.error
from typing import Optional, Any, Dict
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
from app.models.prescription import Prescription, Medication  # type: ignore
from app.models.notification import Notification, NotificationType, NotificationStatus  # type: ignore
from app.utils.security import hash_password  # type: ignore

from app.tasks.reminder_tasks import (  # type: ignore
    parse_medication_frequency,
    compute_next_dose_time,
    send_appointment_reminder_task,
    batch_send_appointment_reminders_task,
    send_medication_reminder_task,
    batch_medication_reminders_task,
)

BASE_URL = "http://127.0.0.1:8000"


def http_request(method: str, endpoint: str, body: Optional[Dict[str, Any]] = None, token: Optional[str] = None):
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


def run_phase17_background_reminder_tests():
    print("=======================================================================")
    print(" RUNNING PHASE 17: BACKGROUND REMINDERS & CELERY PIPELINE TESTS       ")
    print("=======================================================================")

    ts = int(time.time())
    db = SessionLocal()

    try:
        # Provision Test Users, Doctor, Appointments, Prescriptions
        patient_user = User(
            name=f"Reminder Patient {ts}",
            email=f"reminder_patient_{ts}@example.com",
            password_hash=hash_password("PatientPass123!"),
            role=UserRole.PATIENT,
            is_active=True
        )
        doctor_user = User(
            name=f"Dr. Alan Grant {ts}",
            email=f"dr_alan_{ts}@example.com",
            password_hash=hash_password("DoctorPass123!"),
            role=UserRole.DOCTOR,
            is_active=True
        )
        db.add(patient_user)
        db.add(doctor_user)
        db.flush()

        doctor = Doctor(
            user_id=doctor_user.id,
            specialization="Pulmonology",
            experience=12,
            slot_duration=30,
            is_active=True
        )
        db.add(doctor)
        db.flush()

        # -------------------------------------------------------------
        # TEST 1: Appointment Reminder Generation (24h and 1h Windows)
        # -------------------------------------------------------------
        print("\n[TEST 1] Testing Appointment Reminder Generation (24h & 1h)...")
        app_date = date.today() + timedelta(days=1)
        confirmed_app = Appointment(
            patient_id=patient_user.id,  # type: ignore
            doctor_id=doctor.id,  # type: ignore
            appointment_date=app_date,
            start_time=datetime.strptime("09:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("09:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Asthma follow-up check"
        )
        db.add(confirmed_app)
        db.commit()
        db.refresh(confirmed_app)

        # Send 24h Reminder
        res_24h = send_appointment_reminder_task(appointment_id=confirmed_app.id, window_label="24h")
        assert res_24h["status"] == "SENT"
        assert res_24h["patient_email"] == patient_user.email
        assert res_24h["window"] == "24h"

        # Send 1h Reminder
        res_1h = send_appointment_reminder_task(appointment_id=confirmed_app.id, window_label="1h")
        assert res_1h["status"] == "SENT"
        assert res_1h["window"] == "1h"

        # Verify DB Notifications recorded with scheduled_at, sent_at, status
        notif_24h = db.query(Notification).filter(
            Notification.appointment_id == confirmed_app.id,
            Notification.type == NotificationType.APPOINTMENT_REMINDER.value,
            Notification.message.like("%[24H]%")
        ).first()
        assert notif_24h is not None
        assert notif_24h.status == NotificationStatus.SENT.value
        assert notif_24h.scheduled_at is not None
        assert notif_24h.sent_at is not None

        notif_1h = db.query(Notification).filter(
            Notification.appointment_id == confirmed_app.id,
            Notification.type == NotificationType.APPOINTMENT_REMINDER.value,
            Notification.message.like("%[1H]%")
        ).first()
        assert notif_1h is not None
        assert notif_1h.status == NotificationStatus.SENT.value
        print("-> PASSED: 24h and 1h reminders dispatched and tracked in database.")

        # -------------------------------------------------------------
        # TEST 2: Suppression for CANCELLED & COMPLETED Appointments
        # -------------------------------------------------------------
        print("\n[TEST 2] Testing Reminder Suppression for CANCELLED & COMPLETED...")
        cancelled_app = Appointment(
            patient_id=patient_user.id,  # type: ignore
            doctor_id=doctor.id,  # type: ignore
            appointment_date=app_date,
            start_time=datetime.strptime("10:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("10:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CANCELLED,
            cancellation_reason="Patient unavailable"
        )
        completed_app = Appointment(
            patient_id=patient_user.id,  # type: ignore
            doctor_id=doctor.id,  # type: ignore
            appointment_date=app_date,
            start_time=datetime.strptime("11:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("11:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.COMPLETED,
            symptoms="Annual checkup"
        )
        db.add(cancelled_app)
        db.add(completed_app)
        db.commit()

        cancel_res = send_appointment_reminder_task(appointment_id=cancelled_app.id, window_label="24h")
        assert cancel_res["status"] == "SKIPPED"
        assert "CANCELLED" in cancel_res["reason"]

        comp_res = send_appointment_reminder_task(appointment_id=completed_app.id, window_label="24h")
        assert comp_res["status"] == "SKIPPED"
        assert "COMPLETED" in comp_res["reason"]
        print("-> PASSED: CANCELLED and COMPLETED appointments are strictly suppressed.")

        # -------------------------------------------------------------
        # TEST 3: Duplicate Appointment Reminder Prevention (Idempotency)
        # -------------------------------------------------------------
        print("\n[TEST 3] Testing Idempotency & Duplicate Reminder Prevention...")
        dup_res = send_appointment_reminder_task(appointment_id=confirmed_app.id, window_label="24h")
        assert dup_res["status"] == "SKIPPED"
        assert "Duplicate" in dup_res["reason"]
        print("-> PASSED: Duplicate appointment reminder was successfully prevented.")

        # -------------------------------------------------------------
        # TEST 4: Medication Frequency Parsing Engine
        # -------------------------------------------------------------
        print("\n[TEST 4] Testing Medication Frequency Parsing...")
        f1 = parse_medication_frequency("Once daily with water")
        assert f1["type"] == "FIXED"
        assert "08:00" in f1["times"]
        assert f1["interval_hours"] == 24

        f2 = parse_medication_frequency("Twice daily after meals")
        assert f2["type"] == "FIXED"
        assert f2["interval_hours"] == 12
        assert len(f2["times"]) == 2

        f3 = parse_medication_frequency("Three times daily (Morning, Noon, Night)")
        assert f3["type"] == "FIXED"
        assert len(f3["times"]) == 3

        f4 = parse_medication_frequency("Take 1 capsule Every 6 hours as needed")
        assert f4["type"] == "INTERVAL"
        assert f4["interval_hours"] == 6
        assert len(f4["times"]) >= 3

        f5 = parse_medication_frequency("Every 8 hours")
        assert f5["type"] == "INTERVAL"
        assert f5["interval_hours"] == 8
        print("-> PASSED: Frequency parsing handles Once daily, Twice daily, Three times daily, and Every X hours.")

        # -------------------------------------------------------------
        # TEST 5: Medication Next Dose Time Computation
        # -------------------------------------------------------------
        print("\n[TEST 5] Testing Next Dose Time Calculation...")
        base_dt = datetime(2026, 8, 21, 6, 0, tzinfo=timezone.utc)
        next_dose = compute_next_dose_time("Twice daily", current_dt=base_dt)
        assert next_dose.hour == 8
        assert next_dose.day == 21

        base_dt_afternoon = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)
        next_dose_eve = compute_next_dose_time("Twice daily", current_dt=base_dt_afternoon)
        assert next_dose_eve.hour == 20
        assert next_dose_eve.day == 21

        base_dt_late = datetime(2026, 8, 21, 22, 0, tzinfo=timezone.utc)
        next_dose_tmrw = compute_next_dose_time("Twice daily", current_dt=base_dt_late)
        assert next_dose_tmrw.day == 22
        assert next_dose_tmrw.hour == 8
        print("-> PASSED: Next dose timestamps calculated accurately across time slots.")

        # -------------------------------------------------------------
        # TEST 6: Medication Reminder Dispatch & Disabled Exclusion
        # -------------------------------------------------------------
        print("\n[TEST 6] Testing Medication Reminder Dispatch & Disabled Toggle...")
        prescription = Prescription(
            appointment_id=confirmed_app.id,
            doctor_id=doctor.id,  # type: ignore
            patient_id=patient_user.id,  # type: ignore
            notes="Take regular doses with food",
            follow_up_instructions="Review in 14 days"
        )
        db.add(prescription)
        db.flush()

        med_active = Medication(
            prescription_id=prescription.id,
            medication_name="Albuterol Inhaler",
            dosage="90mcg",
            frequency="Twice daily",
            duration="30 days",
            instructions="2 puffs before exercise",
            reminder_enabled=True
        )
        med_disabled = Medication(
            prescription_id=prescription.id,
            medication_name="Ibuprofen",
            dosage="400mg",
            frequency="Every 8 hours",
            duration="5 days",
            instructions="Only if severe headache",
            reminder_enabled=False
        )
        db.add(med_active)
        db.add(med_disabled)
        db.commit()
        db.refresh(med_active)
        db.refresh(med_disabled)

        # Active medication reminder
        med_res = send_medication_reminder_task(medication_id=med_active.id, dose_time="08:00")
        assert med_res["status"] == "SENT"
        assert med_res["patient_id"] == patient_user.id

        # Disabled medication reminder should be skipped
        med_dis_res = send_medication_reminder_task(medication_id=med_disabled.id)
        assert med_dis_res["status"] == "SKIPPED"
        assert "disabled" in med_dis_res["reason"].lower()
        print("-> PASSED: Active medication dispatched; disabled medication successfully excluded.")

        # -------------------------------------------------------------
        # TEST 7: Duplicate Medication Reminder Prevention
        # -------------------------------------------------------------
        print("\n[TEST 7] Testing Duplicate Medication Reminder Prevention...")
        med_dup_res = send_medication_reminder_task(medication_id=med_active.id, dose_time="08:00")
        assert med_dup_res["status"] == "SKIPPED"
        assert "Duplicate" in med_dup_res["reason"]
        print("-> PASSED: Duplicate medication reminder prevented for same dosage window.")

        # -------------------------------------------------------------
        # TEST 8: Batch Reminder Dispatcher Tasks
        # -------------------------------------------------------------
        print("\n[TEST 8] Testing Batch Celery Reminder Jobs...")
        batch_app_res = batch_send_appointment_reminders_task(hours_ahead=24, window_label="24h")
        assert batch_app_res["status"] == "COMPLETED"
        assert isinstance(batch_app_res["reminders_sent_count"], int)

        batch_med_res = batch_medication_reminders_task()
        assert batch_med_res["status"] == "COMPLETED"
        assert isinstance(batch_med_res["reminders_sent_count"], int)
        print("-> PASSED: Batch Celery reminder jobs executed cleanly.")

        # -------------------------------------------------------------
        # TEST 9: Patient Medication & Reminder API Endpoints
        # -------------------------------------------------------------
        print("\n[TEST 9] Testing Patient Medication & Reminder API Endpoints...")
        # Authenticate as patient
        patient_login = {
            "email": patient_user.email,
            "password": "PatientPass123!"
        }
        status, auth_data = http_request("POST", "/api/auth/login", body=patient_login)
        assert status == 200, f"Patient login failed: {auth_data}"
        patient_token = auth_data["access_token"]

        # GET /api/patient/medications
        status, meds_res = http_request("GET", "/api/patient/medications", token=patient_token)
        assert status == 200, f"Get medications failed: {meds_res}"
        assert meds_res["success"] is True
        assert meds_res["total_medications"] >= 2
        med_items = meds_res["medications"]
        albuterol = next(m for m in med_items if m["id"] == med_active.id)
        assert albuterol["reminder_enabled"] is True
        assert "next_dose_display" in albuterol

        # PATCH /api/patient/medications/{id}/toggle-reminder
        status, toggle_res = http_request("PATCH", f"/api/patient/medications/{med_active.id}/toggle-reminder", token=patient_token)
        assert status == 200, f"Toggle failed: {toggle_res}"
        assert toggle_res["reminder_enabled"] is False

        # Toggle back to True
        status, toggle_back_res = http_request("PATCH", f"/api/patient/medications/{med_active.id}/toggle-reminder", token=patient_token)
        assert status == 200
        assert toggle_back_res["reminder_enabled"] is True

        # GET /api/patient/reminders/upcoming
        status, upcoming_res = http_request("GET", "/api/patient/reminders/upcoming", token=patient_token)
        assert status == 200, f"Upcoming reminders failed: {upcoming_res}"
        assert upcoming_res["success"] is True
        assert len(upcoming_res["upcoming_appointments"]) >= 1
        assert len(upcoming_res["upcoming_medications"]) >= 1
        print("-> PASSED: Patient medications list, toggle controls, and upcoming schedule APIs verified.")

        # -------------------------------------------------------------
        # TEST 10: Diagnostic Reminder Trigger Endpoint
        # -------------------------------------------------------------
        print("\n[TEST 10] Testing Diagnostic Reminder Trigger Endpoint...")
        status, trig_app = http_request(
            "POST",
            f"/api/patient/reminders/trigger-now?target_type=appointment&target_id={confirmed_app.id}&window=1h",
            token=patient_token
        )
        assert status == 200, f"Trigger appointment failed: {trig_app}"
        assert trig_app["success"] is True

        status, trig_med = http_request(
            "POST",
            f"/api/patient/reminders/trigger-now?target_type=medication&target_id={med_active.id}",
            token=patient_token
        )
        assert status == 200, f"Trigger medication failed: {trig_med}"
        assert trig_med["success"] is True
        print("-> PASSED: Diagnostic manual reminder trigger endpoint functioning.")

        print("\n=======================================================================")
        print(" ALL 10 PHASE 17 BACKGROUND REMINDER TESTS PASSED!                     ")
        print("=======================================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_phase17_background_reminder_tests()
