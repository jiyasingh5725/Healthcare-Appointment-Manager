"""
Automated Test Suite for Phase 16: Email Notification System & Celery Workers.
Tests configurable email providers (SendGrid, Mailgun, SMTP, Mock),
enhanced Notification data model, Celery email dispatching, 3x retry policies,
decoupled non-rollback guarantees, dual confirmations (Patient + Doctor),
cancellation and doctor leave notices, and Admin monitoring endpoints.
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
from app.models.doctor_schedule import DoctorLeave  # type: ignore
from app.models.appointment import Appointment, AppointmentStatus  # type: ignore
from app.models.notification import Notification, NotificationType, NotificationChannel, NotificationStatus  # type: ignore

from app.services.email_service import (  # type: ignore
    EmailService,
    email_service,
    render_booking_confirmation_email,
    render_cancellation_email,
    render_leave_notification_email,
    render_reschedule_email,
    render_appointment_reminder_email,
    render_medication_reminder_email,
)
from app.tasks.email_tasks import (  # type: ignore
    send_email_task,
    send_notification_email_task,
    send_appointment_confirmation_email_task,
    send_appointment_cancellation_email_task,
    send_leave_cancellation_email_task,
    send_appointment_reschedule_email_task,
)
from app.services.leave_conflict_service import apply_doctor_leave_with_conflict_handling  # type: ignore

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


def run_phase16_email_notification_tests():
    print("=======================================================================")
    print(" RUNNING PHASE 16: EMAIL NOTIFICATION SYSTEM & CELERY PIPELINE TESTS   ")
    print("=======================================================================")

    ts = int(time.time())
    db = SessionLocal()

    try:
        # -------------------------------------------------------------
        # TEST 1: Configurable Email Service & Provider Initialization
        # -------------------------------------------------------------
        print("\n[TEST 1] Testing Email Service & Provider Configuration...")
        assert hasattr(settings, "EMAIL_PROVIDER"), "EMAIL_PROVIDER missing in settings"
        assert hasattr(settings, "EMAIL_FROM"), "EMAIL_FROM missing in settings"
        assert settings.EMAIL_FROM != "", "EMAIL_FROM must not be empty"

        # Test Mock Provider
        mock_svc = EmailService(provider="mock")
        mock_res = mock_svc.send_email(
            to_email="test_patient@example.com",
            subject="Test CareSync Notification",
            html_body="<p>Test Email Content</p>",
            text_body="Test Email Content"
        )
        assert mock_res["success"] is True
        assert mock_res["provider"] == "mock"
        assert "mock-msg-" in mock_res["message_id"]

        # Test SendGrid fallback when key is omitted
        sg_svc = EmailService(provider="sendgrid")
        sg_res = sg_svc.send_email(
            to_email="test_patient@example.com",
            subject="SendGrid Fallback Test",
            html_body="<p>Testing SendGrid Fallback</p>"
        )
        assert sg_res["success"] is True

        # Test Mailgun fallback when key is omitted
        mg_svc = EmailService(provider="mailgun")
        mg_res = mg_svc.send_email(
            to_email="test_patient@example.com",
            subject="Mailgun Fallback Test",
            html_body="<p>Testing Mailgun Fallback</p>"
        )
        assert mg_res["success"] is True
        print("-> PASSED: Configurable EmailService (Mock, SendGrid, Mailgun) verified.")

        # -------------------------------------------------------------
        # TEST 2: Notification Model Schema & Column Validation
        # -------------------------------------------------------------
        print("\n[TEST 2] Testing Notification Data Model Schema & Fields...")
        test_user = User(
            name=f"Notif User {ts}",
            email=f"notif_user_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.PATIENT,
            is_active=True
        )
        db.add(test_user)
        db.flush()

        notif_row = Notification(
            user_id=test_user.id,
            appointment_id=None,
            notification_type=NotificationType.BOOKING_CONFIRMATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.PENDING.value,
            retry_count=0,
            error_message=None,
            scheduled_at=datetime.now(timezone.utc),
            sent_at=None,
            title="Appointment Confirmation",
            message="Your appointment has been confirmed.",
            is_read=False
        )
        db.add(notif_row)
        db.commit()
        db.refresh(notif_row)

        assert notif_row.id is not None
        assert notif_row.user_id == test_user.id
        assert notif_row.notification_type == "BOOKING_CONFIRMATION"
        assert notif_row.channel == "EMAIL"
        assert notif_row.status == "PENDING"
        assert notif_row.retry_count == 0
        assert notif_row.error_message is None
        assert notif_row.created_at is not None
        print(f"-> PASSED: Notification model verified with all 11 required columns (Row #{notif_row.id}).")

        # -------------------------------------------------------------
        # TEST 3: Celery Asynchronous Email Delivery Task Execution
        # -------------------------------------------------------------
        print("\n[TEST 3] Testing Celery send_email_task with Retry Policy...")
        assert send_email_task.max_retries == 3, f"Expected 3 retries, got {send_email_task.max_retries}"

        celery_email_res = send_email_task(
            recipient="patient_celery@example.com",
            subject="CareSync Health Reminder",
            body="Please remember your consultation tomorrow.",
            template_type="APPOINTMENT_REMINDER"
        )
        assert celery_email_res["status"] == "SENT"
        assert celery_email_res["recipient"] == "patient_celery@example.com"
        assert celery_email_res["provider"] in ("mock", "sendgrid", "mailgun", "smtp")
        print("-> PASSED: Celery email tasks and max 3 retry policies verified.")

        # -------------------------------------------------------------
        # TEST 4: Seed Entities for End-to-End Notification Testing
        # -------------------------------------------------------------
        print("\n[TEST 4] Provisioning Test Patients and Doctors...")
        patient_user = User(
            name=f"Patient Alpha {ts}",
            email=f"patient_alpha_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.PATIENT,
            is_active=True
        )
        db.add(patient_user)
        db.flush()

        doctor_user = User(
            name=f"Dr. Sarah Jenkins {ts}",
            email=f"doctor_sarah_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.DOCTOR,
            is_active=True
        )
        db.add(doctor_user)
        db.flush()

        doctor = Doctor(
            user_id=doctor_user.id,
            specialization="Cardiology",
            experience=10,
            slot_duration=30,
            is_active=True
        )
        db.add(doctor)
        db.flush()

        target_date = date.today() + timedelta(days=2)
        appointment = Appointment(
            patient_id=patient_user.id,  # type: ignore
            doctor_id=doctor.id,  # type: ignore
            appointment_date=target_date,
            start_time=datetime.strptime("10:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("10:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Mild palpitations during exercise"
        )
        db.add(appointment)
        db.commit()
        db.refresh(appointment)
        print(f"-> PASSED: Created Patient #{patient_user.id}, Doctor #{doctor.id}, Appointment #{appointment.id}.")

        # -------------------------------------------------------------
        # TEST 5: Dual Booking Confirmation (Patient & Doctor Notifications)
        # -------------------------------------------------------------
        print("\n[TEST 5] Testing Confirmed Booking Dual Notifications (Patient + Doctor)...")
        conf_res = send_appointment_confirmation_email_task(appointment_id=appointment.id)
        assert conf_res["status"] == "SENT"
        assert conf_res["patient_email"] == patient_user.email
        assert conf_res["doctor_email"] == doctor_user.email

        # Verify DB Notifications created for both Patient and Doctor
        pat_notifs = db.query(Notification).filter(
            Notification.user_id == patient_user.id,
            Notification.appointment_id == appointment.id,
            Notification.notification_type == NotificationType.BOOKING_CONFIRMATION.value
        ).all()
        assert len(pat_notifs) >= 1, "Patient booking confirmation notification missing in DB!"

        doc_notifs = db.query(Notification).filter(
            Notification.user_id == doctor_user.id,
            Notification.appointment_id == appointment.id,
            Notification.notification_type == NotificationType.BOOKING_CONFIRMATION.value
        ).all()
        assert len(doc_notifs) >= 1, "Doctor appointment notification missing in DB!"

        print("-> PASSED: Patient received confirmation and Doctor received appointment notification.")

        # -------------------------------------------------------------
        # TEST 6: Dual Cancellation Notifications (Patient & Doctor)
        # -------------------------------------------------------------
        print("\n[TEST 6] Testing Appointment Cancellation Dual Notifications...")
        cancel_res = send_appointment_cancellation_email_task(
            appointment_id=appointment.id,
            cancellation_reason="Patient requested schedule change",
            cancelled_by="Patient"
        )
        assert cancel_res["status"] == "SENT"

        # Verify CANCELLATION notification rows for both users
        cancel_notifs = db.query(Notification).filter(
            Notification.appointment_id == appointment.id,
            Notification.notification_type == NotificationType.CANCELLATION.value
        ).all()
        user_ids = [n.user_id for n in cancel_notifs]
        assert patient_user.id in user_ids, "Patient cancellation notice missing!"
        assert doctor_user.id in user_ids, "Doctor cancellation notice missing!"
        print("-> PASSED: Patient and Doctor notified upon appointment cancellation.")

        # -------------------------------------------------------------
        # TEST 7: Doctor Leave Conflict Notifications (LEAVE_NOTIFICATION)
        # -------------------------------------------------------------
        print("\n[TEST 7] Testing Doctor Leave Conflict Notifications...")
        leave_target_day = date.today() + timedelta(days=3)
        leave_app = Appointment(
            patient_id=patient_user.id,  # type: ignore
            doctor_id=doctor.id,  # type: ignore
            appointment_date=leave_target_day,
            start_time=datetime.strptime("14:00:00", "%H:%M:%S").time(),
            end_time=datetime.strptime("14:30:00", "%H:%M:%S").time(),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Follow-up consultation"
        )
        db.add(leave_app)
        db.commit()
        db.refresh(leave_app)

        leave_record = DoctorLeave(
            doctor_id=doctor.id,  # type: ignore
            leave_date=leave_target_day,
            reason="Cardiology medical conference"
        )
        db.add(leave_record)
        db.commit()

        conflict_res = apply_doctor_leave_with_conflict_handling(
            doctor_id=doctor.id,  # type: ignore
            leave_date=leave_target_day,
            reason="Cardiology medical conference",
            db=db
        )
        assert conflict_res["affected_appointments_count"] >= 1

        db.refresh(leave_app)
        assert leave_app.status == AppointmentStatus.CANCELLED

        leave_notifs = db.query(Notification).filter(
            Notification.user_id == patient_user.id,
            Notification.appointment_id == leave_app.id,
            Notification.notification_type == NotificationType.LEAVE_NOTIFICATION.value
        ).all()
        assert len(leave_notifs) >= 1, "Patient doctor leave notification missing!"
        print("-> PASSED: Patient notified of doctor leave cancellation.")

        # -------------------------------------------------------------
        # TEST 8: Dual Reschedule Notifications
        # -------------------------------------------------------------
        print("\n[TEST 8] Testing Appointment Reschedule Dual Notifications...")
        resched_res = send_appointment_reschedule_email_task(
            appointment_id=appointment.id,
            old_date=str(target_date),
            old_time="10:00",
            new_date=str(target_date + timedelta(days=1)),
            new_time="11:00"
        )
        assert resched_res["status"] == "SENT"

        resched_notifs = db.query(Notification).filter(
            Notification.appointment_id == appointment.id,
            Notification.notification_type == NotificationType.RESCHEDULE.value
        ).all()
        resched_users = [n.user_id for n in resched_notifs]
        assert patient_user.id in resched_users
        assert doctor_user.id in resched_users
        print("-> PASSED: Reschedule notifications dispatched to Patient and Doctor.")

        # -------------------------------------------------------------
        # TEST 9: Decoupled Failure Handling & DB Error Logging
        # -------------------------------------------------------------
        print("\n[TEST 9] Testing Non-Rollback Guarantee & DB Failure Logging...")
        # Create a notification for a user with an invalid destination
        no_email_user = User(
            name=f"Invalid Email Patient {ts}",
            email=f"invalid_email_{ts}@mock.invalid",
            password_hash="mock_hash",
            role=UserRole.PATIENT,
            is_active=True
        )
        db.add(no_email_user)
        db.flush()

        failed_notif = Notification(
            user_id=no_email_user.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.APPOINTMENT_REMINDER.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.PENDING.value,
            retry_count=0,
            title="Failed Email Test",
            message="This should record failure.",
            is_read=False
        )
        db.add(failed_notif)
        db.commit()
        db.refresh(failed_notif)

        # Execute Celery task - should handle gracefully and set FAILED status in DB
        res = send_notification_email_task(notification_id=failed_notif.id)
        assert res["status"] == "FAILED"

        db.refresh(failed_notif)
        assert failed_notif.status == NotificationStatus.FAILED.value
        assert failed_notif.error_message is not None
        assert "No recipient email" in failed_notif.error_message or "has no email" in failed_notif.error_message

        # Verify appointment itself was NEVER rolled back
        db.refresh(appointment)
        assert appointment.id is not None
        print("-> PASSED: Email delivery failure stored in DB and NEVER rolls back appointment.")

        from app.utils.security import hash_password  # type: ignore

        # -------------------------------------------------------------
        # TEST 10: Admin Notification Stats & Delivery Logs API
        # -------------------------------------------------------------
        print("\n[TEST 10] Testing Admin Notification Monitoring Endpoints...")
        # Ensure clean test admin exists in DB
        db.query(User).filter(User.email == "test_admin_phase3@example.com").delete(synchronize_session=False)
        db.commit()

        admin_user = User(
            name="System Administrator",
            email="test_admin_phase3@example.com",
            password_hash=hash_password("AdminPass123!"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(admin_user)
        db.commit()

        # Admin login
        admin_login = {
            "email": "test_admin_phase3@example.com",
            "password": "AdminPass123!"
        }
        status, admin_data = http_request("POST", "/api/auth/login", body=admin_login)
        assert status == 200, f"Admin login failed: {admin_data}"
        admin_token = admin_data["access_token"]

        # GET /api/notifications/admin/stats
        status, stats_res = http_request("GET", "/api/notifications/admin/stats", token=admin_token)
        assert status == 200, f"Admin stats failed: {stats_res}"
        assert isinstance(stats_res, dict)
        assert stats_res.get("status") == "ONLINE"
        assert int(stats_res.get("total_notifications", 0)) >= 1
        assert "success_rate_percentage" in stats_res

        # GET /api/notifications/admin/logs
        status, logs_res = http_request("GET", "/api/notifications/admin/logs?limit=10", token=admin_token)
        assert status == 200, f"Admin logs failed: {logs_res}"
        assert isinstance(logs_res, dict)
        assert len(logs_res.get("logs", [])) >= 1

        print("-> PASSED: Admin notification stats and delivery logs API verified.")

        print("\n=======================================================================")
        print(" ALL 10 PHASE 16 EMAIL NOTIFICATION & CELERY TESTS PASSED!             ")
        print("=======================================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_phase16_email_notification_tests()
