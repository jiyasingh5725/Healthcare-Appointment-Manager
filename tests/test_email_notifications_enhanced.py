"""
Automated Test Suite for Enhanced Email Notifications:
1. Booking Confirmation with Add-to-Calendar (.ics attachment + Web calendar links).
2. Doctor Pre-Visit Clinical Briefing attached to booking email.
3. Post-Visit Patient Care & Prescription Summary Email upon completion.
4. Doctor Completion Confirmation Email upon completion.
5. Non-rollback / non-blocking resilience verification.
"""

import sys
import os
import time
from datetime import date, datetime, timedelta, time as dt_time, timezone

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend"))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import SessionLocal
from app.models.user import User, UserRole
from app.models.doctor import Doctor
from app.models.appointment import Appointment, AppointmentStatus
from app.models.prescription import Prescription, Medication
from app.models.notification import Notification, NotificationType, NotificationChannel, NotificationStatus
from app.services.email_service import (
    email_service,
    render_booking_confirmation_email,
    render_post_visit_patient_email,
    render_appointment_completed_doctor_email,
    generate_calendar_links,
)
from app.tasks.email_tasks import (
    send_appointment_confirmation_email_task,
    send_appointment_completed_notifications_task,
)
from app.services.prescription_service import submit_consultation, create_prescription
from app.schemas.prescription import MedicationItem


def run_enhanced_email_tests():
    print("=======================================================================")
    print(" RUNNING ENHANCED EMAIL NOTIFICATIONS & CALENDAR ATTACHMENT TESTS     ")
    print("=======================================================================")

    db = SessionLocal()
    ts = int(time.time())

    try:
        # Create test Doctor and Patient
        doc_user = User(
            name=f"Dr. Sarah Jenkins {ts}",
            email=f"dr_jenkins_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.DOCTOR,
            phone="+1-555-0199",
            is_active=True
        )
        patient_user = User(
            name=f"John Doe {ts}",
            email=f"john_doe_{ts}@example.com",
            password_hash="mock_hash",
            role=UserRole.PATIENT,
            phone="+1-555-0144",
            is_active=True
        )
        db.add_all([doc_user, patient_user])
        db.flush()

        doctor = Doctor(
            user_id=doc_user.id,
            specialization="Cardiology & Internal Medicine",
            qualification="MD, FACC",
            experience=14,
            slot_duration=30,
            is_active=True
        )
        db.add(doctor)
        db.commit()
        db.refresh(doc_user)
        db.refresh(patient_user)
        db.refresh(doctor)

        # -------------------------------------------------------------
        # TEST 1: Calendar Link Generation & .ICS Attachment
        # -------------------------------------------------------------
        print("\n[TEST 1] Testing Web Calendar Links Generation...")
        start_utc = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)
        end_utc = datetime(2026, 9, 10, 10, 30, tzinfo=timezone.utc)
        links = generate_calendar_links(
            title="Cardiology Consultation",
            start_datetime_utc=start_utc,
            end_datetime_utc=end_utc,
            description="Consultation with Dr. Sarah Jenkins",
            location="CareSync Medical Clinic Room 302"
        )
        assert "google.com/calendar" in links["google"], "Google Calendar link missing"
        assert "outlook.live.com" in links["outlook"], "Outlook Calendar link missing"
        assert "outlook.office.com" in links["office365"], "Office 365 link missing"
        assert "calendar.yahoo.com" in links["yahoo"], "Yahoo Calendar link missing"
        print("-> PASSED: Calendar links correctly generated for Google, Outlook, Office 365, and Yahoo.")

        # -------------------------------------------------------------
        # TEST 2: Appointment Booking Confirmation Dual Emails
        # -------------------------------------------------------------
        print("\n[TEST 2] Testing Booking Confirmation Email Task with Calendar & Pre-Visit Summary...")
        test_app = Appointment(
            patient_id=patient_user.id,
            doctor_id=doctor.id,
            appointment_date=date(2026, 9, 10),
            start_time=dt_time(10, 0),
            end_time=dt_time(10, 30),
            status=AppointmentStatus.CONFIRMED,
            symptoms="Mild chest tightness during moderate exercise for 2 weeks."
        )
        db.add(test_app)
        db.commit()
        db.refresh(test_app)

        # Execute booking confirmation task
        result = send_appointment_confirmation_email_task(appointment_id=test_app.id)
        assert result["status"] == "SENT"
        assert result["patient_email"] == patient_user.email
        assert result["doctor_email"] == doc_user.email
        assert result["has_calendar_attachment"] is True

        # Check DB Notifications
        pat_notif = db.query(Notification).filter(
            Notification.user_id == patient_user.id,
            Notification.appointment_id == test_app.id,
            Notification.type == NotificationType.BOOKING_CONFIRMATION.value
        ).first()
        assert pat_notif is not None, "Patient booking notification not recorded in DB"

        doc_notif = db.query(Notification).filter(
            Notification.user_id == doc_user.id,
            Notification.appointment_id == test_app.id,
            Notification.type == NotificationType.BOOKING_CONFIRMATION.value
        ).first()
        assert doc_notif is not None, "Doctor booking notification not recorded in DB"
        print("-> PASSED: Dual booking confirmation emails sent with .ics attachment and pre-visit clinical briefing.")

        # -------------------------------------------------------------
        # TEST 3: Doctor Completes Appointment & Issues Prescription
        # -------------------------------------------------------------
        print("\n[TEST 3] Testing Post-Visit Email to Patient & Confirmation to Doctor...")
        meds = [
            MedicationItem(
                medication_name="Atorvastatin",
                dosage="20mg",
                frequency="Once daily at bedtime",
                duration="30 days",
                instructions="Take with water after dinner",
                reminder_enabled=True
            ),
            MedicationItem(
                medication_name="Aspirin Low Dose",
                dosage="81mg",
                frequency="Once daily morning",
                duration="30 days",
                instructions="Take with breakfast",
                reminder_enabled=True
            )
        ]

        # Doctor creates prescription and marks COMPLETED
        rx_res = create_prescription(
            appointment_id=test_app.id,
            current_user=doc_user,
            notes="Patient examined. ECG shows sinus rhythm with no ST elevation. Suspected mild angina. Advised lipid panel and stress echocardiogram.",
            follow_up_instructions="Maintain low sodium diet, avoid strenuous exercise until stress test. Follow up in 3 weeks with lab results.",
            medications=meds,
            db=db
        )
        assert rx_res["appointment_id"] == test_app.id

        # Verify task execution for completion
        comp_res = send_appointment_completed_notifications_task(appointment_id=test_app.id)
        assert comp_res["status"] == "SENT"
        assert comp_res["patient_email"] == patient_user.email
        assert comp_res["doctor_email"] == doc_user.email
        assert comp_res["medications_count"] == 2

        # Check rendered patient post-visit email content
        subj_pat, html_pat, text_pat = render_post_visit_patient_email(
            patient_name=patient_user.name,
            doctor_name=doc_user.name,
            specialization=doctor.specialization,
            appointment_date=str(test_app.appointment_date),
            appointment_id=test_app.id,
            visit_summary="ECG normal, advised stress echo.",
            follow_up_instructions="Follow up in 3 weeks.",
            medications=[{"medication_name": "Atorvastatin", "dosage": "20mg", "frequency": "Once daily", "duration": "30 days", "instructions": "After dinner"}]
        )
        assert "Atorvastatin" in html_pat, "Prescription medication missing from patient email HTML"
        assert "Follow up in 3 weeks" in html_pat, "Follow up instructions missing from patient email HTML"
        assert f"#{test_app.id}" in subj_pat, "Appointment ID missing from patient email subject"

        # Check rendered doctor completion email content
        subj_doc, html_doc, text_doc = render_appointment_completed_doctor_email(
            doctor_name=doc_user.name,
            patient_name=patient_user.name,
            specialization=doctor.specialization,
            appointment_date=str(test_app.appointment_date),
            appointment_id=test_app.id,
            notes="ECG normal",
            follow_up_instructions="Follow up in 3 weeks",
            medications_count=2
        )
        assert "COMPLETED" in html_doc, "COMPLETED status missing from doctor email HTML"
        assert patient_user.name in html_doc, "Patient name missing from doctor email HTML"
        print("-> PASSED: Post-visit patient care guide & doctor completion confirmation emails verified.")

        # -------------------------------------------------------------
        # TEST 4: Non-Blocking Resilience on Missing / Disconnected User
        # -------------------------------------------------------------
        print("\n[TEST 4] Testing Failure Resilience & Safe Non-Blocking Execution...")
        invalid_comp_res = send_appointment_completed_notifications_task(appointment_id=999999)
        assert invalid_comp_res["status"] == "SKIPPED", "Task must safely skip non-existent appointments without crashing"
        print("-> PASSED: Non-existent or invalid appointments handled gracefully without blocking.")

        print("\n=======================================================================")
        print(" ALL ENHANCED EMAIL NOTIFICATION & CALENDAR TESTS PASSED SUCCESSFULLY! ")
        print("=======================================================================")

    finally:
        db.close()


if __name__ == "__main__":
    run_enhanced_email_tests()
