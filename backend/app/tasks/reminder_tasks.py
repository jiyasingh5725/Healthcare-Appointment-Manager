import re
import logging
from datetime import datetime, date, time as dt_time, timedelta, timezone
from typing import Optional, Any, Dict, List
from sqlalchemy.orm import joinedload

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.notification import Notification, NotificationType, NotificationChannel, NotificationStatus
from app.models.prescription import Prescription, Medication
from app.models.doctor import Doctor
from app.models.user import User

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Medication Frequency Engine & Helpers
# -----------------------------------------------------------------------------

def parse_medication_frequency(frequency_str: str) -> Dict[str, Any]:
    """
    Parse natural language and standard medical prescription frequencies.
    Supported frequencies:
    - 'Once daily' / '1 time a day'
    - 'Twice daily' / '2 times a day'
    - 'Three times daily' / '3 times a day'
    - 'Every X hours' (e.g. 'Every 4 hours', 'Every 6 hours', 'Every 8 hours', 'Every 12 hours')
    """
    freq_clean = (frequency_str or "").strip().lower()

    # Pattern: Every X hours
    every_x_match = re.search(r"every\s+(\d+)\s*hours?", freq_clean)
    if every_x_match:
        interval_hours = int(every_x_match.group(1))
        # Generate dose times starting from 08:00
        dose_times = []
        cur_hour = 8
        while cur_hour < 24:
            dose_times.append(f"{cur_hour:02d}:00")
            cur_hour += interval_hours
        return {
            "type": "INTERVAL",
            "interval_hours": interval_hours,
            "times": dose_times,
            "description": f"Every {interval_hours} hours",
        }

    if "three times" in freq_clean or "3 times" in freq_clean or "tid" in freq_clean or "thrice" in freq_clean:
        return {
            "type": "FIXED",
            "interval_hours": 6,
            "times": ["08:00", "14:00", "20:00"],
            "description": "Three times daily (Morning, Afternoon, Evening)",
        }

    if "twice" in freq_clean or "2 times" in freq_clean or "bid" in freq_clean:
        return {
            "type": "FIXED",
            "interval_hours": 12,
            "times": ["08:00", "20:00"],
            "description": "Twice daily (Morning, Night)",
        }

    # Default / Once daily
    return {
        "type": "FIXED",
        "interval_hours": 24,
        "times": ["08:00"],
        "description": "Once daily (Morning)",
    }


def compute_next_dose_time(frequency_str: str, current_dt: Optional[datetime] = None) -> datetime:
    """
    Calculate the next upcoming dosage datetime for a given frequency string.
    """
    now = current_dt or datetime.now(timezone.utc)
    parsed = parse_medication_frequency(frequency_str)
    times = parsed.get("times", ["08:00"])

    today_doses = []
    for t_str in times:
        hour, minute = map(int, t_str.split(":"))
        dose_dt = datetime(now.year, now.month, now.day, hour, minute, tzinfo=timezone.utc)
        today_doses.append(dose_dt)

    # Check for remaining doses today
    for dose_dt in sorted(today_doses):
        if dose_dt > now:
            return dose_dt

    # Next dose is the first dose tomorrow
    tomorrow = now + timedelta(days=1)
    first_t_str = times[0]
    h, m = map(int, first_t_str.split(":"))
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, h, m, tzinfo=timezone.utc)


# -----------------------------------------------------------------------------
# Celery Tasks: Appointment Reminders (24h and 1h Windows)
# -----------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.reminder_tasks.send_appointment_reminder_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def send_appointment_reminder_task(
    self,
    appointment_id: int,
    window_label: str = "24h"
) -> Dict[str, Any]:
    """
    Background job to send an upcoming appointment reminder notification to the patient.
    Enforces strict rules:
    - Never send reminders for CANCELLED or COMPLETED appointments.
    - Prevent duplicate reminder sending for the same appointment and window.
    - Store scheduled_at, sent_at, and delivery status in DB.
    """
    db = SessionLocal()
    try:
        appointment = db.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        ).filter(Appointment.id == appointment_id).first()

        if not appointment:
            logger.warning(f"[Celery:Reminder] Appointment #{appointment_id} not found.")
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        # Rule: Do NOT send reminders for CANCELLED or COMPLETED appointments
        if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
            logger.info(
                f"[Celery:Reminder] Appointment #{appointment_id} is {appointment.status.value}, "
                f"skipping reminder."
            )
            return {
                "status": "SKIPPED",
                "appointment_id": appointment_id,
                "reason": f"Appointment status is {appointment.status.value}"
            }

        # Rule: Prevent duplicate reminder sending
        # Check if reminder for this appointment + window already exists
        window_tag = f"[{window_label.upper()}]"
        existing_notif = db.query(Notification).filter(
            Notification.appointment_id == appointment.id,
            Notification.type == NotificationType.APPOINTMENT_REMINDER.value,
            Notification.message.like(f"%{window_tag}%")
        ).first()

        if existing_notif:
            logger.info(
                f"[Celery:Reminder] Duplicate reminder prevented for Appointment #{appointment_id} "
                f"window {window_label}."
            )
            return {
                "status": "SKIPPED",
                "appointment_id": appointment_id,
                "reason": "Duplicate reminder already sent"
            }

        patient = appointment.patient
        doctor_user = appointment.doctor.user if appointment.doctor else None
        doctor_name = doctor_user.name if doctor_user else "Physician"
        patient_name = patient.name if patient else "Patient"
        patient_email = patient.email if patient else ""

        now_utc = datetime.now(timezone.utc)
        scheduled_at = now_utc
        sent_at = now_utc

        timing_desc = "tomorrow" if "24" in window_label else "in 1 hour"
        title = f"Appointment Reminder ({window_label.upper()}): Dr. {doctor_name}"
        message = (
            f"{window_tag} Dear {patient_name}, this is a reminder for your upcoming consultation with "
            f"Dr. {doctor_name} scheduled for {appointment.appointment_date} at {appointment.start_time.strftime('%H:%M')} "
            f"({timing_desc}). Please arrive 10 minutes prior to your session."
        )

        notif = Notification(
            user_id=appointment.patient_id,
            appointment_id=appointment.id,
            title=title,
            message=message,
            type=NotificationType.APPOINTMENT_REMINDER.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            email_job_status="SENT",
            scheduled_at=scheduled_at,
            sent_at=sent_at,
            retry_count=0,
            is_read=False,
            calendar_job_status="SYNCED"
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)

        logger.info(f"[Celery:Reminder] Dispatched {window_label} reminder for Appointment #{appointment_id} to {patient_email}")
        return {
            "status": "SENT",
            "appointment_id": appointment_id,
            "patient_id": appointment.patient_id,
            "patient_email": patient_email,
            "notification_id": notif.id,
            "window": window_label,
            "scheduled_at": str(scheduled_at),
            "sent_at": str(sent_at)
        }
    except Exception as e:
        logger.error(f"[Celery:Reminder] Failed to send reminder for #{appointment_id}: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.reminder_tasks.batch_send_appointment_reminders_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2
)
def batch_send_appointment_reminders_task(
    self,
    hours_ahead: int = 24,
    window_label: str = "24h"
) -> Dict[str, Any]:
    """
    Periodic batch job scanning all CONFIRMED appointments due for reminders in the specified window.
    Strictly excludes CANCELLED and COMPLETED appointments and prevents duplicates.
    """
    db = SessionLocal()
    try:
        today = date.today()
        # Filter window target date
        target_date = today + timedelta(days=max(1, hours_ahead // 24))

        upcoming_appointments = db.query(Appointment).options(
            joinedload(Appointment.patient),
            joinedload(Appointment.doctor).joinedload(Doctor.user)
        ).filter(
            Appointment.status == AppointmentStatus.CONFIRMED,
            Appointment.appointment_date >= today,
            Appointment.appointment_date <= target_date
        ).all()

        reminded_ids = []
        skipped_count = 0

        for app in upcoming_appointments:
            # Rule: Skip if not CONFIRMED
            if app.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
                skipped_count += 1
                continue

            window_tag = f"[{window_label.upper()}]"
            # Rule: Prevent duplicate reminder sending
            existing_notif = db.query(Notification).filter(
                Notification.appointment_id == app.id,
                Notification.type == NotificationType.APPOINTMENT_REMINDER.value,
                Notification.message.like(f"%{window_tag}%")
            ).first()

            if not existing_notif:
                res = send_appointment_reminder_task(appointment_id=app.id, window_label=window_label)
                if res.get("status") == "SENT":
                    reminded_ids.append(app.id)
            else:
                skipped_count += 1

        logger.info(
            f"[Celery:Reminder] Batch {window_label} scan completed. "
            f"Reminded: {len(reminded_ids)}, Skipped: {skipped_count}"
        )
        return {
            "status": "COMPLETED",
            "hours_ahead": hours_ahead,
            "window_label": window_label,
            "reminders_sent_count": len(reminded_ids),
            "skipped_count": skipped_count,
            "appointment_ids": reminded_ids
        }
    finally:
        db.close()


# -----------------------------------------------------------------------------
# Celery Tasks: Medication Reminders & Dosage Schedules
# -----------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.reminder_tasks.send_medication_reminder_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def send_medication_reminder_task(
    self,
    medication_id: int,
    dose_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Background job to send medication dosage reminder notification.
    - Checks reminder_enabled is True.
    - Prevents duplicate reminders for the same dosage time on the same date.
    - Records scheduled_at, sent_at, and status.
    """
    db = SessionLocal()
    try:
        med = db.query(Medication).options(
            joinedload(Medication.prescription).joinedload(Prescription.appointment).joinedload(Appointment.patient),
            joinedload(Medication.prescription).joinedload(Prescription.appointment).joinedload(Appointment.doctor).joinedload(Doctor.user)
        ).filter(Medication.id == medication_id).first()

        if not med:
            logger.warning(f"[Celery:Medication] Medication #{medication_id} not found.")
            return {"status": "SKIPPED", "reason": "Medication not found"}

        # Rule: Do not send reminder if reminder_enabled is False
        if not med.reminder_enabled:
            logger.info(f"[Celery:Medication] Reminders disabled for medication #{medication_id}.")
            return {"status": "SKIPPED", "reason": "Reminders disabled for this medication"}

        prescription = med.prescription
        appointment = prescription.appointment if prescription else None
        target_patient = appointment.patient if appointment else None
        target_patient_id = target_patient.id if target_patient else None

        if not target_patient_id:
            return {"status": "SKIPPED", "reason": "Target patient not found"}

        now_utc = datetime.now(timezone.utc)
        today_date_str = now_utc.strftime("%Y-%m-%d")
        dose_tag = f"[{dose_time or now_utc.strftime('%H:%M')}|{today_date_str}]"

        # Rule: Prevent duplicate reminder sending for the same dose window today
        existing_notif = db.query(Notification).filter(
            Notification.user_id == target_patient_id,
            Notification.type == NotificationType.MEDICATION_REMINDER.value,
            Notification.message.like(f"%Medication #{med.id}%"),
            Notification.message.like(f"%{dose_tag}%")
        ).first()

        if existing_notif:
            logger.info(f"[Celery:Medication] Duplicate medication reminder prevented for #{med.id} ({dose_tag}).")
            return {
                "status": "SKIPPED",
                "medication_id": med.id,
                "reason": "Duplicate medication reminder already sent for this dose window"
            }

        instructions_text = f" - Instructions: {med.instructions}" if med.instructions else ""
        title = f"Medication Reminder: {med.medication_name} ({med.dosage})"
        message = (
            f"{dose_tag} (Medication #{med.id}) Time to take your prescribed medication: {med.medication_name} "
            f"({med.dosage}). Frequency: {med.frequency}. Prescribed duration: {med.duration}{instructions_text}."
        )

        scheduled_at = now_utc
        sent_at = now_utc

        notif = Notification(
            user_id=target_patient_id,
            appointment_id=appointment.id if appointment else None,
            title=title,
            message=message,
            type=NotificationType.MEDICATION_REMINDER.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            email_job_status="SENT",
            scheduled_at=scheduled_at,
            sent_at=sent_at,
            retry_count=0,
            is_read=False,
            calendar_job_status="PREPARED"
        )
        db.add(notif)
        db.commit()
        db.refresh(notif)

        logger.info(f"[Celery:Medication] Dispatched medication reminder for #{med.id} to patient #{target_patient_id}")
        return {
            "status": "SENT",
            "medication_id": med.id,
            "medication_name": med.medication_name,
            "patient_id": target_patient_id,
            "notification_id": notif.id,
            "scheduled_at": str(scheduled_at),
            "sent_at": str(sent_at)
        }
    except Exception as e:
        logger.error(f"[Celery:Medication] Failed to send medication reminder for #{medication_id}: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.reminder_tasks.batch_medication_reminders_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=2
)
def batch_medication_reminders_task(self) -> Dict[str, Any]:
    """
    Batch job to scan all active prescriptions with reminder_enabled=True and dispatch medication reminders.
    Strictly checks reminder_enabled and deduplicates.
    """
    db = SessionLocal()
    try:
        medications = db.query(Medication).options(
            joinedload(Medication.prescription).joinedload(Prescription.appointment)
        ).filter(
            Medication.reminder_enabled == True
        ).all()

        reminded_ids = []
        skipped_count = 0

        for med in medications:
            prescription = med.prescription
            appointment = prescription.appointment if prescription else None
            if not appointment or not med.reminder_enabled:
                skipped_count += 1
                continue

            res = send_medication_reminder_task(medication_id=med.id)
            if res.get("status") == "SENT":
                reminded_ids.append(med.id)
            else:
                skipped_count += 1

        logger.info(
            f"[Celery:Medication] Batch medication reminders completed. "
            f"Reminded: {len(reminded_ids)}, Skipped: {skipped_count}"
        )
        return {
            "status": "COMPLETED",
            "reminders_sent_count": len(reminded_ids),
            "skipped_count": skipped_count,
            "medication_ids": reminded_ids
        }
    finally:
        db.close()


# Batch task aliases
schedule_appointment_reminders_batch_task = batch_send_appointment_reminders_task
schedule_medication_reminders_batch_task = batch_medication_reminders_task
