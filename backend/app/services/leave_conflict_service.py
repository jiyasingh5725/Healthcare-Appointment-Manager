from datetime import date
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_

from app.models.appointment import Appointment, AppointmentStatus
from app.models.notification import Notification
from app.models.doctor import Doctor
from app.models.user import User


def process_leave_conflicts(
    doctor_id: int,
    leave_date: date,
    doctor_name: str,
    db: Session
) -> dict:
    """
    Handle appointment conflicts when a doctor is marked on leave:
    1. Transactionally find all active/confirmed appointments on leave_date.
    2. Mark affected appointments as CANCELLED with reason 'Doctor unavailable due to leave'.
    3. Preserve appointment records in the database.
    4. Create notification records and prepare email/calendar jobs.
    5. Ensure appointment cancellation remains committed even if notification dispatch encounters an error.
    """
    # 1. Transaction 1: Cancel active conflicting appointments
    conflicting_appointments = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    ).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == leave_date,
        Appointment.status.in_([
            AppointmentStatus.CONFIRMED,
            AppointmentStatus.HOLD,
            AppointmentStatus.RESCHEDULED
        ])
    ).all()

    affected_summary = []
    patients_to_notify = []
    affected_ids = []

    for app in conflicting_appointments:
        app.status = AppointmentStatus.CANCELLED
        app.cancellation_reason = "Doctor unavailable due to leave"
        affected_ids.append(app.id)

        patient_name = app.patient.name if app.patient else f"Patient #{app.patient_id}"
        patient_email = app.patient.email if app.patient else ""
        patient_phone = app.patient.phone if app.patient else None

        item = {
            "appointment_id": app.id,
            "patient_id": app.patient_id,
            "patient_name": patient_name,
            "patient_email": patient_email,
            "patient_phone": patient_phone,
            "start_time": str(app.start_time),
            "end_time": str(app.end_time),
            "status": "CANCELLED",
            "cancellation_reason": app.cancellation_reason,
        }
        affected_summary.append(item)
        patients_to_notify.append(item)

    db.commit()

    # 2. Transaction 2: Notification & Background Job Preparation (Isolated)
    notifications_count = 0
    calendar_jobs_count = 0

    try:
        from app.models.notification import NotificationType, NotificationChannel, NotificationStatus
        from app.tasks import dispatch_async_task, send_leave_cancellation_email_task, cancel_calendar_event_task

        for app in conflicting_appointments:
            notif = Notification(
                user_id=app.patient_id,
                appointment_id=app.id,
                title="Appointment Cancelled - Doctor Unavailable",
                message=(
                    f"Your consultation with Dr. {doctor_name} on {leave_date} "
                    f"at {app.start_time} has been cancelled because the doctor is on leave."
                ),
                notification_type=NotificationType.LEAVE_NOTIFICATION.value,
                channel=NotificationChannel.EMAIL.value,
                status=NotificationStatus.PENDING.value,
                is_read=False,
                calendar_job_status="PREPARED",
            )
            db.add(notif)
            notifications_count += 1
            calendar_jobs_count += 1

        db.commit()

        # Asynchronously dispatch emails via Celery
        for p in patients_to_notify:
            try:
                dispatch_async_task(
                    send_leave_cancellation_email_task,
                    p["appointment_id"],
                    p["patient_email"],
                    p["patient_name"],
                    p["doctor_name"],
                    p["appointment_date"],
                    p["start_time"],
                    reason
                )
                dispatch_async_task(
                    cancel_calendar_event_task,
                    p["appointment_id"],
                    None,
                    f"Doctor on leave: {reason}"
                )
            except Exception:
                pass

    except Exception:
        db.rollback()
        # Appointment cancellation remains successful

    return {
        "affected_appointments_count": len(affected_summary),
        "affected_appointments": affected_summary,
        "patients_to_notify": patients_to_notify,
        "notifications_prepared": notifications_count,
        "calendar_sync_jobs_prepared": calendar_jobs_count,
    }


def apply_doctor_leave_with_conflict_handling(
    doctor_id: int,
    leave_date: date,
    reason: str = "Doctor unavailable due to leave",
    db: Session = None
) -> dict:
    """Helper alias resolving doctor name and running conflict processing."""
    doctor = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.id == doctor_id).first()
    doctor_name = doctor.user.name if (doctor and doctor.user) else f"Doctor #{doctor_id}"
    return process_leave_conflicts(doctor_id=doctor_id, leave_date=leave_date, doctor_name=doctor_name, db=db)

