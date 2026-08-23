import logging
from datetime import datetime, timezone, timedelta, date, time as dt_time
from typing import Optional, Any, Dict, cast
from sqlalchemy.orm import joinedload

from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.notification import Notification
from app.models.doctor import Doctor
from app.models.user import User
from app.models.calendar_event import CalendarEvent
from app.services.calendar_service import calendar_service

logger = logging.getLogger(__name__)


def generate_ical_content(
    appointment: Appointment,
    is_cancellation: bool = False,
    cancellation_reason: Optional[str] = None
) -> str:
    """
    Generate an RFC 5545 compliant iCalendar (.ics) string for an appointment.
    """
    now_utc_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    
    # Combine date and time
    dt_start = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.start_time))
    dt_end = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.end_time))
    
    dt_start_str = dt_start.strftime("%Y%m%dT%H%M%S")
    dt_end_str = dt_end.strftime("%Y%m%dT%H%M%S")
    
    doctor_name = appointment.doctor.user.name if (appointment.doctor and appointment.doctor.user) else "Doctor"
    patient_name = appointment.patient.name if appointment.patient else "Patient"
    specialization = appointment.doctor.specialization if appointment.doctor else "General Consultation"
    
    uid = f"appointment-{appointment.id}-caresync@hospital.org"
    method = "CANCEL" if is_cancellation else "REQUEST"
    status = "CANCELLED" if is_cancellation else "CONFIRMED"
    sequence = "1" if is_cancellation else "0"
    
    summary = f"Doctor Appointment - Dr. {doctor_name}"
    if is_cancellation:
        summary = f"CANCELLED: {summary}"

    description = (
        f"Patient: {patient_name}\\n"
        f"Doctor: Dr. {doctor_name} ({specialization})\\n"
        f"Status: {status}\\n"
    )
    if is_cancellation and cancellation_reason:
        description += f"Cancellation Reason: {cancellation_reason}\\n"
    elif appointment.symptoms:
        description += f"Reported Symptoms: {appointment.symptoms}\\n"
    
    description += "Platform: CareSync Healthcare Manager"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CareSync Healthcare//Appointment Calendar//EN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_utc_str}",
        f"DTSTART:{dt_start_str}",
        f"DTEND:{dt_end_str}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{description}",
        "LOCATION:CareSync Medical Clinic & Telehealth Room",
        f"STATUS:{status}",
        f"SEQUENCE:{sequence}",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    return "\r\n".join(lines)


@celery_app.task(
    name="app.tasks.calendar_tasks.sync_appointment_to_calendar_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def sync_appointment_to_calendar_task(self, appointment_id: int) -> Dict[str, Any]:
    """
    Background job to synchronize a confirmed appointment to Google Calendar & iCal.
    Guaranteed non-rollback: failures are captured and never crash core appointment state.
    """
    db = SessionLocal()
    try:
        # Create Google Calendar event record via calendar_service
        gcal_result = calendar_service.create_appointment_calendar_event(appointment_id=appointment_id, db=db)

        # Update notification tracking
        db.query(Notification).filter(
            Notification.appointment_id == appointment_id
        ).update({"calendar_job_status": "SYNCED"}, synchronize_session=False)
        db.commit()

        logger.info(f"[Celery:Calendar] Successfully synced Google Calendar event for Appointment #{appointment_id}")
        return {
            "status": "SYNCED",
            "appointment_id": appointment_id,
            "google_event_id": gcal_result.get("google_event_id"),
            "title": gcal_result.get("title"),
            "start": gcal_result.get("start"),
            "end": gcal_result.get("end"),
        }
    except Exception as e:
        logger.error(f"[Celery:Calendar] Failed to sync calendar for Appointment #{appointment_id}: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.calendar_tasks.cancel_calendar_event_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def cancel_calendar_event_task(
    self,
    appointment_id: int,
    calendar_event_id: Optional[str] = None,
    cancellation_reason: Optional[str] = "Cancelled by patient or clinic"
) -> Dict[str, Any]:
    """
    Background job to cancel Google Calendar event upon appointment cancellation.
    """
    db = SessionLocal()
    try:
        cancel_result = calendar_service.cancel_appointment_calendar_event(appointment_id=appointment_id, db=db)

        db.query(Notification).filter(
            Notification.appointment_id == appointment_id
        ).update({"calendar_job_status": "CANCELLED"}, synchronize_session=False)
        db.commit()

        logger.info(f"[Celery:Calendar] Cancelled Google Calendar event for Appointment #{appointment_id}")
        return {
            "status": "CANCELLED",
            "appointment_id": appointment_id,
            "google_event_id": cancel_result.get("google_event_id"),
            "reason": cancellation_reason
        }
    except Exception as e:
        logger.error(f"[Celery:Calendar] Failed to cancel calendar event for #{appointment_id}: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.calendar_tasks.update_google_calendar_event_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3
)
def update_google_calendar_event_task(self, appointment_id: int) -> Dict[str, Any]:
    """
    Background job to update Google Calendar event when an appointment is rescheduled.
    """
    db = SessionLocal()
    try:
        update_result = calendar_service.update_appointment_calendar_event(appointment_id=appointment_id, db=db)
        db.query(Notification).filter(
            Notification.appointment_id == appointment_id
        ).update({"calendar_job_status": "SYNCED"}, synchronize_session=False)
        db.commit()

        logger.info(f"[Celery:Calendar] Updated Google Calendar event for Appointment #{appointment_id}")
        return {
            "status": update_result.get("status", "SYNCED"),
            "appointment_id": appointment_id,
            "google_event_id": update_result.get("google_event_id"),
            "start": update_result.get("start"),
            "end": update_result.get("end"),
        }
    except Exception as e:
        logger.error(f"[Celery:Calendar] Failed to update calendar event for #{appointment_id}: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


# Google Calendar task aliases
sync_google_calendar_event_task = sync_appointment_to_calendar_task
cancel_google_calendar_event_task = cancel_calendar_event_task
reschedule_google_calendar_event_task = update_google_calendar_event_task
