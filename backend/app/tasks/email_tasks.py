import logging
from datetime import datetime, timezone, date, time as dt_time
from typing import Any, Optional, cast

from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.notification import Notification, NotificationChannel, NotificationStatus, NotificationType
from app.models.user import User
from app.models.prescription import Prescription, Medication
from app.models.ai_summary import AISummary
from app.services.email_service import (
    email_service,
    render_appointment_reminder_email,
    render_booking_confirmation_email,
    render_cancellation_email,
    render_leave_notification_email,
    render_medication_reminder_email,
    render_reschedule_email,
    render_post_visit_patient_email,
    render_appointment_completed_doctor_email,
    generate_calendar_links,
)
from app.tasks.calendar_tasks import generate_ical_content
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.email_tasks.send_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=3,
    retry_jitter=True,
)
def send_email_task(
    self,
    recipient: str,
    subject: str,
    body: str,
    template_type: str = "GENERIC",
    metadata: Optional[dict[str, Any]] = None,
    html_body: Optional[str] = None,
    attachments: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Base asynchronous email delivery task with automatic retry and exponential backoff.
    Dispatches through configured email provider (SendGrid, Mailgun, SMTP, Mock).
    """
    attempt = self.request.retries + 1
    logger.info(f"[Celery:Email] Sending '{template_type}' email to {recipient} (Attempt {attempt}/4)")

    html = html_body or f"<p>{body.replace(chr(10), '<br>')}</p>"
    result = email_service.send_email(
        to_email=recipient,
        subject=subject,
        html_body=html,
        text_body=body,
        attachments=attachments,
    )

    if not result.get("success"):
        error_msg = result.get("error", "Email dispatch error")
        logger.warning(f"[Celery:Email] Attempt {attempt} failed for {recipient}: {error_msg}")
        raise Exception(error_msg)

    return {
        "status": "SENT",
        "recipient": recipient,
        "subject": subject,
        "template_type": template_type,
        "provider": result.get("provider"),
        "message_id": result.get("message_id"),
        "retries": self.request.retries,
        "metadata": metadata or {},
    }


@celery_app.task(
    name="app.tasks.email_tasks.send_notification_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_notification_email_task(self, notification_id: int) -> dict[str, Any]:
    """
    Asynchronous task to process a Notification DB record and dispatch the email.
    Tracks status, retry count, and errors in the Notification record.
    """
    attempt = self.request.retries + 1
    db = SessionLocal()
    try:
        notif = (
            db.query(Notification)
            .options(joinedload(Notification.user), joinedload(Notification.appointment))
            .filter(Notification.id == notification_id)
            .first()
        )

        if not notif:
            logger.warning(f"[Celery:Notification] Notification #{notification_id} not found.")
            return {"status": "SKIPPED", "reason": "Notification not found"}

        user = notif.user
        if not user or not user.email or user.email.endswith(".invalid"):
            notif.status = NotificationStatus.FAILED.value
            notif.error_message = "Recipient has no email address or domain is invalid"
            db.commit()
            return {"status": "FAILED", "reason": "No recipient email"}

        notif.status = NotificationStatus.RETRYING.value if attempt > 1 else NotificationStatus.PENDING.value
        notif.retry_count = self.request.retries
        db.commit()

        # Send Email
        html_body = f"<p>{notif.message.replace(chr(10), '<br>')}</p>"
        res = email_service.send_email(
            to_email=user.email,
            subject=notif.title,
            html_body=html_body,
            text_body=notif.message,
        )

        if res.get("success"):
            now_utc = datetime.now(timezone.utc)
            notif.status = NotificationStatus.SENT.value
            notif.sent_at = now_utc
            notif.error_message = None
            db.commit()
            logger.info(f"[Celery:Notification] Notification #{notification_id} successfully sent to {user.email}")
            return {"status": "SENT", "notification_id": notification_id, "recipient": user.email}
        else:
            error_reason = res.get("error", "Unknown delivery failure")
            notif.error_message = error_reason
            if attempt >= 3:
                notif.status = NotificationStatus.FAILED.value
            else:
                notif.status = NotificationStatus.RETRYING.value
            db.commit()
            raise Exception(error_reason)

    except Exception as exc:
        db.rollback()
        # Ensure error status is recorded
        try:
            err_db = SessionLocal()
            err_notif = err_db.query(Notification).filter(Notification.id == notification_id).first()
            if err_notif:
                err_notif.retry_count = self.request.retries
                err_notif.error_message = str(exc)
                if self.request.retries >= 3:
                    err_notif.status = NotificationStatus.FAILED.value
                else:
                    err_notif.status = NotificationStatus.RETRYING.value
                err_db.commit()
            err_db.close()
        except Exception:
            pass
        raise exc
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.email_tasks.send_appointment_confirmation_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_appointment_confirmation_email_task(self, appointment_id: int) -> dict[str, Any]:
    """
    Dispatches dual booking confirmation notifications (Patient + Doctor) for a confirmed appointment.
    Includes Add-to-Calendar links, .ics attachment, and doctor pre-visit briefing.
    """
    db = SessionLocal()
    try:
        appointment = (
            db.query(Appointment)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user),
            )
            .filter(Appointment.id == appointment_id)
            .first()
        )

        if not appointment:
            logger.warning(f"[Celery:Email] Appointment #{appointment_id} not found for confirmation.")
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        patient = appointment.patient
        doctor = appointment.doctor
        doctor_user = doctor.user if doctor else None

        if not patient or not doctor or not doctor_user:
            return {"status": "SKIPPED", "reason": "Missing patient or doctor record"}

        patient_name = patient.name
        doctor_name = doctor_user.name
        specialization = doctor.specialization or "General Medicine"
        app_date_str = str(appointment.appointment_date)
        app_time_str = appointment.start_time.strftime("%H:%M")
        app_end_time_str = appointment.end_time.strftime("%H:%M") if appointment.end_time else None

        # Build calendar links and .ics attachment
        dt_start = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.start_time))
        dt_end = datetime.combine(cast(date, appointment.appointment_date), cast(dt_time, appointment.end_time))
        dt_start_utc = dt_start.replace(tzinfo=timezone.utc)
        dt_end_utc = dt_end.replace(tzinfo=timezone.utc)

        cal_title = f"Doctor Appointment - Dr. {doctor_name} ({specialization})"
        cal_desc = f"CareSync Healthcare Consultation #{appointment.id} with Dr. {doctor_name}. Patient: {patient_name}."
        calendar_links = generate_calendar_links(
            title=cal_title,
            start_datetime_utc=dt_start_utc,
            end_datetime_utc=dt_end_utc,
            description=cal_desc,
            location="CareSync Medical Clinic"
        )

        attachments = None
        try:
            ics_content = generate_ical_content(appointment)
            if ics_content:
                attachments = [{
                    "filename": f"appointment-{appointment.id}.ics",
                    "content": ics_content,
                    "content_type": "text/calendar"
                }]
        except Exception as ics_err:
            logger.warning(f"[Celery:Email] Could not generate .ics for Appointment #{appointment_id}: {ics_err}")

        # Gather patient context for doctor pre-visit summary
        patient_info = {
            "name": patient.name,
            "email": patient.email,
            "phone": getattr(patient, "phone", None),
        }

        past_records = []
        try:
            past_apps = (
                db.query(Appointment)
                .filter(
                    Appointment.patient_id == patient.id,
                    Appointment.id != appointment.id,
                    Appointment.status == AppointmentStatus.COMPLETED
                )
                .order_by(Appointment.appointment_date.desc())
                .limit(3)
                .all()
            )
            for pa in past_apps:
                past_records.append(f"{pa.appointment_date}: Consultation #{pa.id} ({pa.symptoms or 'General Checkup'})")
        except Exception:
            pass

        ai_summary_obj = (
            db.query(AISummary)
            .filter(AISummary.appointment_id == appointment.id)
            .order_by(AISummary.created_at.desc())
            .first()
        )

        previsit_summary = {
            "chief_complaint": appointment.symptoms or "General medical checkup and consultation",
            "symptoms": appointment.symptoms or "General consultation",
            "medical_history": past_records,
            "urgency_level": ai_summary_obj.urgency_level if ai_summary_obj else None,
            "summary_text": ai_summary_obj.summary_text if ai_summary_obj else None,
        }

        # 1. Patient Notification & Email (with Add to Calendar links & .ics attachment)
        pat_subj, pat_html, pat_text = render_booking_confirmation_email(
            patient_name=patient_name,
            doctor_name=doctor_name,
            specialization=specialization,
            appointment_date=app_date_str,
            start_time=app_time_str,
            appointment_id=appointment.id,
            is_doctor_copy=False,
            end_time=app_end_time_str,
            appointment_type="In-Person Consultation",
            calendar_links=calendar_links,
            symptoms=appointment.symptoms,
        )

        pat_notif = Notification(
            user_id=patient.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.BOOKING_CONFIRMATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=pat_subj,
            message=pat_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(pat_notif)

        # Dispatch Patient Email
        email_service.send_email(
            to_email=patient.email,
            subject=pat_subj,
            html_body=pat_html,
            text_body=pat_text,
            attachments=attachments,
        )

        # 2. Doctor Notification & Email (with Pre-Visit Briefing & .ics attachment)
        doc_subj, doc_html, doc_text = render_booking_confirmation_email(
            patient_name=patient_name,
            doctor_name=doctor_name,
            specialization=specialization,
            appointment_date=app_date_str,
            start_time=app_time_str,
            appointment_id=appointment.id,
            is_doctor_copy=True,
            end_time=app_end_time_str,
            appointment_type="In-Person Consultation",
            calendar_links=calendar_links,
            previsit_summary=previsit_summary,
            patient_info=patient_info,
            symptoms=appointment.symptoms,
        )

        doc_notif = Notification(
            user_id=doctor_user.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.BOOKING_CONFIRMATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=doc_subj,
            message=doc_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(doc_notif)

        # Dispatch Doctor Email
        email_service.send_email(
            to_email=doctor_user.email,
            subject=doc_subj,
            html_body=doc_html,
            text_body=doc_text,
            attachments=attachments,
        )

        db.commit()
        logger.info(f"[Celery:Email] Dual booking confirmations sent for Appointment #{appointment_id} (Patient & Doctor).")

        return {
            "status": "SENT",
            "appointment_id": appointment_id,
            "patient_email": patient.email,
            "doctor_email": doctor_user.email,
            "has_calendar_attachment": bool(attachments),
        }
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.email_tasks.send_appointment_cancellation_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_appointment_cancellation_email_task(
    self,
    appointment_id: int,
    cancellation_reason: str = "Appointment cancelled",
    cancelled_by: str = "Patient",
) -> dict[str, Any]:
    """
    Dispatches dual cancellation notifications to Patient and Doctor.
    """
    db = SessionLocal()
    try:
        appointment = (
            db.query(Appointment)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user),
            )
            .filter(Appointment.id == appointment_id)
            .first()
        )

        if not appointment:
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        patient = appointment.patient
        doctor_user = appointment.doctor.user if (appointment.doctor and appointment.doctor.user) else None

        if not patient or not doctor_user:
            return {"status": "SKIPPED", "reason": "Incomplete user record"}

        app_date_str = str(appointment.appointment_date)
        app_time_str = appointment.start_time.strftime("%H:%M")

        # 1. Patient Cancellation Notification & Email
        pat_subj, pat_html, pat_text = render_cancellation_email(
            recipient_name=patient.name,
            patient_name=patient.name,
            doctor_name=doctor_user.name,
            appointment_date=app_date_str,
            start_time=app_time_str,
            appointment_id=appointment.id,
            reason=cancellation_reason,
            cancelled_by=cancelled_by,
        )
        pat_notif = Notification(
            user_id=patient.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.CANCELLATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=pat_subj,
            message=pat_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(pat_notif)
        email_service.send_email(to_email=patient.email, subject=pat_subj, html_body=pat_html, text_body=pat_text)

        # 2. Doctor Cancellation Notification & Email
        doc_subj, doc_html, doc_text = render_cancellation_email(
            recipient_name=doctor_user.name,
            patient_name=patient.name,
            doctor_name=doctor_user.name,
            appointment_date=app_date_str,
            start_time=app_time_str,
            appointment_id=appointment.id,
            reason=cancellation_reason,
            cancelled_by=cancelled_by,
        )
        doc_notif = Notification(
            user_id=doctor_user.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.CANCELLATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=doc_subj,
            message=doc_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(doc_notif)
        email_service.send_email(to_email=doctor_user.email, subject=doc_subj, html_body=doc_html, text_body=doc_text)

        db.commit()
        logger.info(f"[Celery:Email] Dual cancellation emails sent for Appointment #{appointment_id}.")
        return {"status": "SENT", "appointment_id": appointment_id}
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.email_tasks.send_leave_cancellation_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_leave_cancellation_email_task(
    self,
    appointment_id: int,
    patient_email: str,
    patient_name: str,
    doctor_name: str,
    appointment_date: str,
    start_time: str,
    reason: str = "Doctor unavailable due to leave",
) -> dict[str, Any]:
    """
    Background job to notify a patient that their appointment was cancelled due to doctor leave.
    """
    subj, html, text = render_leave_notification_email(
        patient_name=patient_name,
        doctor_name=doctor_name,
        appointment_date=appointment_date,
        start_time=start_time,
        appointment_id=appointment_id,
        reason=reason,
    )

    db = SessionLocal()
    try:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        patient_id = appointment.patient_id if appointment else None
        if patient_id:
            notif = Notification(
                user_id=patient_id,
                appointment_id=appointment_id,
                notification_type=NotificationType.LEAVE_NOTIFICATION.value,
                channel=NotificationChannel.EMAIL.value,
                status=NotificationStatus.SENT.value,
                title=subj,
                message=text,
                is_read=False,
                sent_at=datetime.now(timezone.utc),
            )
            db.add(notif)
            db.commit()
    finally:
        db.close()

    email_service.send_email(
        to_email=patient_email,
        subject=subj,
        html_body=html,
        text_body=text,
    )

    logger.info(f"[Celery:Email] Dispatched leave cancellation notice for Appointment #{appointment_id} to {patient_email}")
    return {
        "status": "SENT",
        "appointment_id": appointment_id,
        "recipient": patient_email,
        "subject": subj,
        "reason": reason,
    }


@celery_app.task(
    name="app.tasks.email_tasks.send_appointment_reschedule_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_appointment_reschedule_email_task(
    self,
    appointment_id: int,
    old_date: str,
    old_time: str,
    new_date: str,
    new_time: str,
) -> dict[str, Any]:
    """
    Dispatches dual reschedule notifications to Patient and Doctor.
    """
    db = SessionLocal()
    try:
        appointment = (
            db.query(Appointment)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user),
            )
            .filter(Appointment.id == appointment_id)
            .first()
        )
        if not appointment:
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        patient = appointment.patient
        doctor_user = appointment.doctor.user if (appointment.doctor and appointment.doctor.user) else None

        if not patient or not doctor_user:
            return {"status": "SKIPPED", "reason": "Missing patient or doctor"}

        # 1. Patient Reschedule Email
        pat_subj, pat_html, pat_text = render_reschedule_email(
            recipient_name=patient.name,
            patient_name=patient.name,
            doctor_name=doctor_user.name,
            old_date=old_date,
            old_time=old_time,
            new_date=new_date,
            new_time=new_time,
            appointment_id=appointment.id,
        )
        pat_notif = Notification(
            user_id=patient.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.RESCHEDULE.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=pat_subj,
            message=pat_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(pat_notif)
        email_service.send_email(to_email=patient.email, subject=pat_subj, html_body=pat_html, text_body=pat_text)

        # 2. Doctor Reschedule Email
        doc_subj, doc_html, doc_text = render_reschedule_email(
            recipient_name=doctor_user.name,
            patient_name=patient.name,
            doctor_name=doctor_user.name,
            old_date=old_date,
            old_time=old_time,
            new_date=new_date,
            new_time=new_time,
            appointment_id=appointment.id,
        )
        doc_notif = Notification(
            user_id=doctor_user.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.RESCHEDULE.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=doc_subj,
            message=doc_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(doc_notif)
        email_service.send_email(to_email=doctor_user.email, subject=doc_subj, html_body=doc_html, text_body=doc_text)

        db.commit()
        logger.info(f"[Celery:Email] Dual reschedule emails dispatched for Appointment #{appointment_id}.")
        return {"status": "SENT", "appointment_id": appointment_id}
    finally:
        db.close()


@celery_app.task(
    name="app.tasks.email_tasks.send_consultation_summary_email_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_consultation_summary_email_task(
    self,
    appointment_id: int,
    patient_email: str,
    patient_name: str,
    doctor_name: str,
    summary_text: str,
) -> dict[str, Any]:
    """
    Background job to email the post-visit care guide & summary to the patient.
    """
    subject = f"Your Care & Recovery Guide from Dr. {doctor_name}"
    body = (
        f"Dear {patient_name},\n\n"
        f"Thank you for visiting Dr. {doctor_name}. Here is your patient care summary:\n\n"
        f"{summary_text}\n\n"
        "You can view your complete medication schedule and follow-up guidance on the CareSync portal."
    )

    email_service.send_email(
        to_email=patient_email,
        subject=subject,
        html_body=f"<p>{body.replace(chr(10), '<br>')}</p>",
        text_body=body,
    )

    logger.info(f"[Celery:Email] Dispatched consultation summary email for Appointment #{appointment_id} to {patient_email}")
    return {
        "status": "SENT",
        "appointment_id": appointment_id,
        "recipient": patient_email,
        "subject": subject,
    }


@celery_app.task(
    name="app.tasks.email_tasks.send_appointment_completed_notifications_task",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_appointment_completed_notifications_task(self, appointment_id: int) -> dict[str, Any]:
    """
    Dispatches post-visit care guide & prescription email to the Patient,
    and completion confirmation email to the Doctor.
    """
    db = SessionLocal()
    try:
        appointment = (
            db.query(Appointment)
            .options(
                joinedload(Appointment.patient),
                joinedload(Appointment.doctor).joinedload(Doctor.user),
            )
            .filter(Appointment.id == appointment_id)
            .first()
        )

        if not appointment:
            logger.warning(f"[Celery:Email] Appointment #{appointment_id} not found for completion notification.")
            return {"status": "SKIPPED", "reason": "Appointment not found"}

        patient = appointment.patient
        doctor = appointment.doctor
        doctor_user = doctor.user if doctor else None

        if not patient or not doctor or not doctor_user:
            return {"status": "SKIPPED", "reason": "Missing patient or doctor record"}

        patient_name = patient.name
        doctor_name = doctor_user.name
        specialization = doctor.specialization or "General Medicine"
        app_date_str = str(appointment.appointment_date)

        # Retrieve prescription and medication items if recorded
        prescription = (
            db.query(Prescription)
            .options(joinedload(Prescription.medications))
            .filter(Prescription.appointment_id == appointment_id)
            .first()
        )

        visit_summary = prescription.notes if prescription else None
        follow_up_instructions = prescription.follow_up_instructions if prescription else None

        medications_list = []
        if prescription and prescription.medications:
            for med in prescription.medications:
                medications_list.append({
                    "medication_name": med.medication_name,
                    "dosage": med.dosage,
                    "frequency": med.frequency,
                    "duration": med.duration,
                    "instructions": med.instructions,
                })

        # 1. Post-Visit Patient Email
        pat_subj, pat_html, pat_text = render_post_visit_patient_email(
            patient_name=patient_name,
            doctor_name=doctor_name,
            specialization=specialization,
            appointment_date=app_date_str,
            appointment_id=appointment.id,
            visit_summary=visit_summary,
            follow_up_instructions=follow_up_instructions,
            medications=medications_list,
        )

        pat_notif = Notification(
            user_id=patient.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.MEDICATION_REMINDER.value if medications_list else NotificationType.BOOKING_CONFIRMATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=pat_subj,
            message=pat_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(pat_notif)

        email_service.send_email(
            to_email=patient.email,
            subject=pat_subj,
            html_body=pat_html,
            text_body=pat_text,
        )

        # 2. Appointment Completed Doctor Email
        doc_subj, doc_html, doc_text = render_appointment_completed_doctor_email(
            doctor_name=doctor_name,
            patient_name=patient_name,
            specialization=specialization,
            appointment_date=app_date_str,
            appointment_id=appointment.id,
            notes=visit_summary,
            follow_up_instructions=follow_up_instructions,
            medications_count=len(medications_list),
        )

        doc_notif = Notification(
            user_id=doctor_user.id,
            appointment_id=appointment.id,
            notification_type=NotificationType.BOOKING_CONFIRMATION.value,
            channel=NotificationChannel.EMAIL.value,
            status=NotificationStatus.SENT.value,
            title=doc_subj,
            message=doc_text,
            is_read=False,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(doc_notif)

        db.commit()
        logger.info(f"[Celery:Email] Appointment completion emails sent for Appointment #{appointment_id} (Patient & Doctor).")

        return {
            "status": "SENT",
            "appointment_id": appointment_id,
            "patient_email": patient.email,
            "doctor_email": doctor_user.email,
            "medications_count": len(medications_list),
        }
    finally:
        db.close()


# Backward compatibility aliases
send_booking_confirmation_notifications_task = send_appointment_confirmation_email_task
send_appointment_cancellation_notifications_task = send_appointment_cancellation_email_task
send_consultation_completed_notifications_task = send_appointment_completed_notifications_task
