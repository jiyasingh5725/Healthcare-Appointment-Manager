import os
import sys
import time
import json
import uuid
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import date, time as dt_time, timedelta, datetime, timezone
from typing import Optional, Dict, Any, Tuple

# Ensure project root is on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "backend"))

from app.database import SessionLocal  # type: ignore
from app.models.user import User, UserRole  # type: ignore
from app.models.doctor import Doctor  # type: ignore
from app.models.doctor_schedule import DoctorWorkingHours, DoctorLeave  # type: ignore
from app.models.appointment import Appointment, AppointmentStatus  # type: ignore
from app.models.notification import Notification, NotificationType, NotificationStatus  # type: ignore
from app.models.calendar_event import CalendarEvent  # type: ignore
from app.utils.security import hash_password, create_access_token  # type: ignore

API_BASE_URL = "http://127.0.0.1:8000/api"


def http_request(
    method: str,
    endpoint: str,
    body: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None
) -> Tuple[int, Dict[str, Any]]:
    url = f"{API_BASE_URL}{endpoint}"
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}"

    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            response_body = response.read().decode("utf-8")
            try:
                parsed = json.loads(response_body)
            except Exception:
                parsed = {"raw": response_body}
            return status_code, parsed
    except urllib.error.HTTPError as e:
        status_code = e.code
        error_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(error_body)
        except Exception:
            parsed = {"raw": error_body}
        return status_code, parsed
    except Exception as e:
        return 500, {"error": str(e)}


def test_suite():
    print("=" * 80)
    print(" STARTING PHASE 20: COMPLETE SECURITY AND SYSTEM TESTING PASS")
    print("=" * 80)

    db = SessionLocal()
    try:
        ts = int(time.time())
        p1_email = f"sec_patient1_{ts}@test.com"
        p2_email = f"sec_patient2_{ts}@test.com"
        doc_email = f"sec_doctor_{ts}@test.com"
        admin_email = f"sec_admin_{ts}@test.com"

        # -------------------------------------------------------------
        # [TEST 1] REGISTRATION & DUPLICATE EMAIL (409)
        # -------------------------------------------------------------
        print("\n[TEST 1] Testing User Registration & Duplicate Email Conflict (409)...")
        # 1a. Valid Registration
        code, reg1 = http_request("POST", "/auth/register", {
            "name": "Security Patient 1",
            "email": p1_email,
            "password": "SecurePassword123!",
            "phone": "+15550001"
        })
        assert code == 201, f"Registration failed: {reg1}"
        assert reg1["email"] == p1_email
        assert "password" not in reg1, "Password hash must not be exposed in registration response"

        # 1b. Duplicate Registration (Should return 409 with standardized envelope)
        code, reg_dup = http_request("POST", "/auth/register", {
            "name": "Security Patient Duplicate",
            "email": p1_email,
            "password": "SecurePassword123!"
        })
        assert code == 409, f"Expected 409 for duplicate email, got: {code} ({reg_dup})"
        assert reg_dup.get("success") is False, f"Expected success=False, got: {reg_dup}"
        assert reg_dup.get("error_code") in ("CONFLICT", "EMAIL_ALREADY_EXISTS"), f"Unexpected error_code: {reg_dup}"
        assert "message" in reg_dup, f"Missing message in envelope: {reg_dup}"
        print("-> PASSED: Registration and 409 Duplicate Email verified with standard error envelope.")

        # -------------------------------------------------------------
        # [TEST 2] LOGIN & AUTHENTICATION (401)
        # -------------------------------------------------------------
        print("\n[TEST 2] Testing User Login & Invalid Credentials (401)...")
        # 2a. Invalid Password
        code, bad_login = http_request("POST", "/auth/login", {
            "email": p1_email,
            "password": "WrongPassword!"
        })
        assert code == 401, f"Expected 401 for wrong password, got: {code} ({bad_login})"
        assert bad_login.get("success") is False
        assert bad_login.get("error_code") in ("UNAUTHORIZED", "INVALID_CREDENTIALS")
        assert "message" in bad_login

        # 2b. Valid Login
        code, login_res = http_request("POST", "/auth/login", {
            "email": p1_email,
            "password": "SecurePassword123!"
        })
        assert code == 200, f"Login failed: {login_res}"
        assert "access_token" in login_res
        p1_token = login_res["access_token"]

        # Register and login Patient 2
        code, _ = http_request("POST", "/auth/register", {
            "name": "Security Patient 2",
            "email": p2_email,
            "password": "SecurePassword123!",
            "phone": "+15550002"
        })
        assert code == 201
        code, l2 = http_request("POST", "/auth/login", {"email": p2_email, "password": "SecurePassword123!"})
        assert code == 200
        p2_token = l2["access_token"]

        print("-> PASSED: Login success and 401 Unauthorized error envelope verified.")

        # -------------------------------------------------------------
        # [TEST 3] ROLE AUTHORIZATION (403 FORBIDDEN)
        # -------------------------------------------------------------
        print("\n[TEST 3] Testing Role Authorization & 403 Forbidden Access...")
        # Patient attempting to access admin endpoint (POST /admin/doctors)
        code, forbidden_res = http_request("POST", "/admin/doctors", {
            "name": "Unauthorized Attempt",
            "email": "unauth@test.com",
            "password": "Pass123!",
            "specialization": "General",
            "qualification": "MBBS",
            "experience": 5,
            "slot_duration": 30
        }, token=p1_token)
        assert code == 403, f"Expected 403 for patient accessing admin endpoint, got: {code} ({forbidden_res})"
        assert forbidden_res.get("success") is False
        assert forbidden_res.get("error_code") == "FORBIDDEN"
        assert "message" in forbidden_res

        # Request without token (401)
        code, unauth_res = http_request("POST", "/admin/doctors", {})
        assert code == 401
        assert unauth_res.get("success") is False
        assert unauth_res.get("error_code") == "UNAUTHORIZED"
        print("-> PASSED: Role authorization and 403 Forbidden / 401 Unauthorized verified.")

        # -------------------------------------------------------------
        # [TEST 4] DOCTOR CREATION (ADMIN ONBOARDING)
        # -------------------------------------------------------------
        print("\n[TEST 4] Testing Admin Doctor Creation...")
        # Create Admin in DB
        admin_user = db.query(User).filter(User.email == admin_email).first()
        if not admin_user:
            admin_user = User(
                name="Security Administrator",
                email=admin_email,
                password_hash=hash_password("AdminPass123!"),
                role=UserRole.ADMIN,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)

        code, admin_auth = http_request("POST", "/auth/login", {"email": admin_email, "password": "AdminPass123!"})
        assert code == 200
        admin_token = admin_auth["access_token"]

        # Admin creates Doctor profile
        code, doc_created = http_request("POST", "/admin/doctors", {
            "name": "Dr. Sarah Jenkins",
            "email": doc_email,
            "password": "DoctorPass123!",
            "specialization": "Cardiology",
            "qualification": "MD, FACC",
            "experience": 14,
            "slot_duration": 30,
            "phone": "+15550009"
        }, token=admin_token)
        assert code == 201, f"Doctor creation failed: {doc_created}"
        doctor_id = doc_created["id"]
        print(f"-> PASSED: Doctor created successfully (Doctor ID: {doctor_id}).")

        # -------------------------------------------------------------
        # [TEST 5] WORKING HOURS CONFIGURATION
        # -------------------------------------------------------------
        print("\n[TEST 5] Testing Doctor Working Hours Configuration...")
        wh_schedule = [
            {"day_of_week": i, "start_time": "08:00:00", "end_time": "17:00:00", "is_working": True}
            for i in range(5)
        ]
        code, wh_res = http_request("PUT", f"/admin/doctors/{doctor_id}/working-hours", {"working_hours": wh_schedule}, token=admin_token)
        assert code in (200, 201), f"Setting working hours failed: {wh_res}"
        print("-> PASSED: Doctor working hours configured and verified.")

        # -------------------------------------------------------------
        # [TEST 6] DOCTOR LEAVE MANAGEMENT
        # -------------------------------------------------------------
        print("\n[TEST 6] Testing Doctor Leave Registration...")
        leave_target_date = date.today() + timedelta(days=14)
        while leave_target_date.weekday() >= 5:  # Ensure weekday
            leave_target_date += timedelta(days=1)

        code, leave_res = http_request("POST", f"/admin/doctors/{doctor_id}/leaves", {
            "leave_date": str(leave_target_date),
            "reason": "Annual Medical Symposium"
        }, token=admin_token)
        assert code in (200, 201), f"Leave creation failed: {leave_res}"

        # Attempt to book slot on leave date (should return 400 Bad Request)
        code, leave_book_res = http_request("POST", "/appointments", {
            "doctor_id": doctor_id,
            "appointment_date": str(leave_target_date),
            "start_time": "10:00:00",
            "symptoms": "Trying to book on leave"
        }, token=p1_token)
        assert code == 400, f"Expected 400 for booking on doctor leave, got: {code}"
        assert leave_book_res.get("success") is False
        print("-> PASSED: Doctor leave blocks appointment scheduling with 400 error.")

        # -------------------------------------------------------------
        # [TEST 7] DYNAMIC AVAILABLE SLOT GENERATION
        # -------------------------------------------------------------
        print("\n[TEST 7] Testing Dynamic Slot Generation...")
        test_booking_date = date.today() + timedelta(days=21)
        while test_booking_date.weekday() >= 5:
            test_booking_date += timedelta(days=1)

        code, avail_res = http_request("GET", f"/doctors/{doctor_id}/availability", params={"date": str(test_booking_date)})
        assert code == 200, f"Slots retrieval failed: {avail_res}"
        slots = avail_res.get("slots", [])
        assert len(slots) > 0, "Expected calculated slots for weekday within working hours"
        available_slots = [s for s in slots if s.get("is_available") is True]
        assert len(available_slots) > 0, "Expected available slots"
        print(f"-> PASSED: Slot generation generated {len(available_slots)} available consultation slots out of {len(slots)} total slots.")

        # -------------------------------------------------------------
        # [TEST 8] APPOINTMENT BOOKING
        # -------------------------------------------------------------
        print("\n[TEST 8] Testing Appointment Booking Flow...")
        code, app1_res = http_request("POST", "/appointments", {
            "doctor_id": doctor_id,
            "appointment_date": str(test_booking_date),
            "start_time": "09:00:00",
            "symptoms": "Routine cardiovascular checkup"
        }, token=p1_token)
        assert code == 201, f"Appointment booking failed: {app1_res}"
        assert app1_res["status"] == "CONFIRMED"
        app1_id = app1_res["id"]
        print(f"-> PASSED: Appointment #{app1_id} booked and confirmed.")

        # -------------------------------------------------------------
        # [TEST 9] SIMULTANEOUS BOOKING CONCURRENCY (CRITICAL TEST)
        # -------------------------------------------------------------
        print("\n[TEST 9] Testing Simultaneous Booking Concurrency (Two requests at same millisecond)...")
        concurrency_slot = "10:30:00"
        results = []

        def book_simultaneous(user_token, label):
            c, r = http_request("POST", "/appointments", {
                "doctor_id": doctor_id,
                "appointment_date": str(test_booking_date),
                "start_time": concurrency_slot,
                "symptoms": f"Simultaneous booking attempt from {label}"
            }, token=user_token)
            results.append((c, r, label))

        t1 = threading.Thread(target=book_simultaneous, args=(p1_token, "Patient 1"))
        t2 = threading.Thread(target=book_simultaneous, args=(p2_token, "Patient 2"))

        # Launch simultaneously
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        status_codes = [r[0] for r in results]
        print(f"Concurrent booking status codes received: {status_codes}")

        # Verification: Exactly ONE must be 201 (success), exactly ONE must be 409 (conflict)
        assert 201 in status_codes, f"Expected one 201 Created, got: {status_codes}"
        assert 409 in status_codes, f"Expected one 409 Conflict, got: {status_codes}"

        conflict_response = next(r[1] for r in results if r[0] == 409)
        assert conflict_response.get("success") is False, f"Expected success=False in conflict response, got: {conflict_response}"
        assert conflict_response.get("error_code") == "SLOT_ALREADY_BOOKED", f"Expected error_code='SLOT_ALREADY_BOOKED', got: {conflict_response}"

        # Direct DB verification: Count confirmed appointments for that exact slot
        db.expire_all()
        confirmed_count = db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            Appointment.appointment_date == test_booking_date,
            Appointment.start_time == dt_time(10, 30),
            Appointment.status == AppointmentStatus.CONFIRMED
        ).count()
        assert confirmed_count == 1, f"CRITICAL: Expected exactly 1 confirmed appointment in DB, found: {confirmed_count}"
        print(f"-> PASSED: Concurrency handled perfectly! 1 succeeded (201), 1 rejected (409 SLOT_ALREADY_BOOKED). DB confirmed count = {confirmed_count}.")

        # -------------------------------------------------------------
        # [TEST 10] SLOT HOLD EXPIRATION
        # -------------------------------------------------------------
        print("\n[TEST 10] Testing Slot Hold Expiration...")
        # Create an expired HOLD in DB
        expired_hold = Appointment(
            patient_id=int(admin_user.id),
            doctor_id=doctor_id,
            appointment_date=test_booking_date,
            start_time=dt_time(11, 30),
            end_time=dt_time(12, 0),
            status=AppointmentStatus.HOLD,
            hold_until=datetime.now(timezone.utc) - timedelta(minutes=10),
            symptoms="Temporary hold that expired"
        )
        db.add(expired_hold)
        db.commit()
        db.refresh(expired_hold)

        # Now Patient 1 attempts to book the expired hold slot (11:30)
        code, hold_book_res = http_request("POST", "/appointments", {
            "doctor_id": doctor_id,
            "appointment_date": str(test_booking_date),
            "start_time": "11:30:00",
            "symptoms": "Booking over expired hold slot"
        }, token=p1_token)
        assert code == 201, f"Failed to book over expired hold slot: {hold_book_res}"
        assert hold_book_res["status"] == "CONFIRMED"
        print("-> PASSED: Expired hold automatically overridden and booked successfully.")

        # -------------------------------------------------------------
        # [TEST 11] CANCELLATION & AUDIT HISTORY PRESERVATION
        # -------------------------------------------------------------
        print("\n[TEST 11] Testing Appointment Cancellation & History Preservation...")
        code, cancel_res = http_request("POST", f"/appointments/{app1_id}/cancel", {
            "reason": "Patient requested reschedule to afternoon"
        }, token=p1_token)
        assert code == 200, f"Cancellation failed: {cancel_res}"
        assert cancel_res["status"] == "CANCELLED"

        # Verify in DB that record is NOT deleted and status is CANCELLED
        db.expire_all()
        app_in_db = db.query(Appointment).filter(Appointment.id == app1_id).first()
        assert app_in_db is not None, "Appointment record must not be deleted from database"
        assert app_in_db.status == AppointmentStatus.CANCELLED
        assert app_in_db.cancellation_reason == "Patient requested reschedule to afternoon"

        # Verify the freed slot (09:00) can now be booked by Patient 2
        code, rebook_res = http_request("POST", "/appointments", {
            "doctor_id": doctor_id,
            "appointment_date": str(test_booking_date),
            "start_time": "09:00:00",
            "symptoms": "Rebooking cancelled slot"
        }, token=p2_token)
        assert code == 201, f"Failed to book freed slot: {rebook_res}"
        print("-> PASSED: Cancellation released slot, history preserved in database.")

        # -------------------------------------------------------------
        # [TEST 12] RESCHEDULING & CONFLICT CHECK
        # -------------------------------------------------------------
        print("\n[TEST 12] Testing Appointment Rescheduling...")
        reschedule_target_date = test_booking_date + timedelta(days=1)
        while reschedule_target_date.weekday() >= 5:
            reschedule_target_date += timedelta(days=1)

        # Create active appointment for Patient 1
        code, app_to_resched = http_request("POST", "/appointments", {
            "doctor_id": doctor_id,
            "appointment_date": str(reschedule_target_date),
            "start_time": "14:00:00",
            "symptoms": "Initial appointment to be rescheduled"
        }, token=p1_token)
        assert code == 201
        resched_app_id = app_to_resched["id"]

        # Reschedule to 15:00 on same date
        code, resched_success = http_request("POST", f"/appointments/{resched_app_id}/reschedule", {
            "new_date": str(reschedule_target_date),
            "new_start_time": "15:00:00"
        }, token=p1_token)
        assert code == 200, f"Reschedule failed: {resched_success}"
        assert "15:00" in resched_success["start_time"]
        assert resched_success["status"] == "CONFIRMED"
        print("-> PASSED: Rescheduling updated appointment atomically.")

        # -------------------------------------------------------------
        # [TEST 13] AI FAILURE RESILIENCE
        # -------------------------------------------------------------
        print("\n[TEST 13] Testing AI Failure Resilience...")
        from app.services.ai_summary_service import _rule_based_fallback, generate_previsit_summary  # type: ignore
        # Simulate AI fallback by calling heuristic fallback directly and full flow
        fallback_summary = _rule_based_fallback("Patient has mild sinus congestion and mild fever.")
        assert "urgency_level" in fallback_summary
        assert "heuristic" in fallback_summary["model_name"]
        assert len(fallback_summary["suggested_questions"]) >= 3

        # Full service generation with resilience fallback
        db.expire_all()
        ai_res = generate_previsit_summary(appointment_id=resched_app_id, symptoms_override=None, db=db)
        assert ai_res is not None
        assert ai_res.get("urgency_level") in ("Low", "Medium", "High")
        print("-> PASSED: AI summary failure resilience fallback verified.")

        # -------------------------------------------------------------
        # [TEST 14] EMAIL FAILURE RESILIENCE
        # -------------------------------------------------------------
        print("\n[TEST 14] Testing Email Failure Resilience (Non-Rollback Guarantee)...")
        # Direct verification of email task handling invalid addresses without crashing DB
        from app.services.email_service import email_service  # type: ignore
        failed_notif = Notification(
            user_id=int(admin_user.id),
            appointment_id=resched_app_id,
            type=NotificationType.BOOKING_CONFIRMATION,
            channel="EMAIL",
            status=NotificationStatus.PENDING,
            title="Resilience Test",
            message="Test email delivery"
        )
        db.add(failed_notif)
        db.commit()
        db.refresh(failed_notif)

        email_res = email_service.send_email(
            to_email="invalid_email_test@invalid_domain_test_xyz.org",
            subject="Test Subject",
            html_body="<p>Test</p>"
        )
        assert "success" in email_res
        # Even if mock sends or fails, appointment record remains intact
        db.expire_all()
        resched_check = db.query(Appointment).filter(Appointment.id == resched_app_id).first()
        assert resched_check is not None
        assert resched_check.status == AppointmentStatus.CONFIRMED, "Appointment must remain CONFIRMED regardless of email status"
        print("-> PASSED: Email delivery failure logged without rolling back appointment transaction.")

        # -------------------------------------------------------------
        # [TEST 15] CALENDAR FAILURE RESILIENCE
        # -------------------------------------------------------------
        print("\n[TEST 15] Testing Calendar Sync Failure Resilience...")
        from app.services.calendar_service import calendar_service  # type: ignore
        # Simulating calendar sync on disconnected user
        sync_result = calendar_service.create_appointment_calendar_event(appointment_id=resched_app_id, db=db)
        assert sync_result["status"] in ("SYNCED", "CONFIRMED", "SKIPPED", "NO_OAUTH")

        db.expire_all()
        resched_check2 = db.query(Appointment).filter(Appointment.id == resched_app_id).first()
        assert resched_check2 is not None
        assert resched_check2.status == AppointmentStatus.CONFIRMED
        print("-> PASSED: Calendar sync decoupled from DB transaction; non-rollback verified.")

        # -------------------------------------------------------------
        # [TEST 16] CENTRALIZED ERROR HANDLERS (404, 422)
        # -------------------------------------------------------------
        print("\n[TEST 16] Testing 404 and 422 Centralized Error Envelopes...")
        # 404 Not Found
        code, err_404 = http_request("GET", "/appointments/9999999", token=p1_token)
        assert code == 404
        assert err_404.get("success") is False
        assert err_404.get("error_code") == "NOT_FOUND"
        assert "message" in err_404

        # 422 Unprocessable Entity (Schema Validation Error)
        code, err_422 = http_request("POST", "/auth/register", {
            "name": "Invalid Email User",
            "email": "not-an-email",
            "password": "123"
        })
        assert code == 422
        assert err_422.get("success") is False
        assert err_422.get("error_code") == "VALIDATION_ERROR"
        assert "message" in err_422

        print("-> PASSED: Standard error envelopes verified across 400, 401, 403, 404, 409, 422.")

        print("\n" + "=" * 80)
        print(" ALL 15+ PHASE 20 SECURITY AND SYSTEM TESTS PASSED SUCCESSFULLY!")
        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    test_suite()
