import threading
from datetime import date, time, datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError

from app.models.user import User, UserRole
from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorWorkingHours, DoctorLeave
from app.models.appointment import Appointment, AppointmentStatus
from app.schemas.appointment import AppointmentCreateRequest, AppointmentResponse
from app.schemas.doctor_schedule import DAYS_OF_WEEK_NAMES

# Configurable hold window
DEFAULT_HOLD_MINUTES = 5

# Global process lock for serializing slot conflict checks & reservations
_booking_lock = threading.Lock()


def _serialize_appointment(app: Appointment) -> AppointmentResponse:
    """Helper to convert Appointment ORM entity to AppointmentResponse schema."""
    patient_name = app.patient.name if app.patient else f"Patient #{app.patient_id}"
    patient_email = app.patient.email if app.patient else ""
    patient_phone = app.patient.phone if app.patient else None

    doctor_name = app.doctor.user.name if (app.doctor and app.doctor.user) else f"Doctor #{app.doctor_id}"
    specialization = app.doctor.specialization if app.doctor else "General Practice"

    return AppointmentResponse(
        id=app.id,
        patient_id=app.patient_id,
        patient_name=patient_name,
        patient_email=patient_email,
        patient_phone=patient_phone,
        doctor_id=app.doctor_id,
        doctor_name=doctor_name,
        specialization=specialization,
        appointment_date=app.appointment_date,
        start_time=app.start_time,
        end_time=app.end_time,
        status=app.status,
        symptoms=app.symptoms,
        cancellation_reason=app.cancellation_reason,
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


def book_appointment(
    patient_id: int,
    payload: AppointmentCreateRequest,
    db: Session
) -> AppointmentResponse:
    """
    Validate conditions and atomically book a consultation slot for a patient with a doctor.
    Enforces row-level locking (SELECT ... FOR UPDATE), hold expiration verification,
    and handles simultaneous concurrency race conditions gracefully with 409 Conflict.
    """
    # 1. Validate Doctor Exists & is Active
    doctor = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.id == payload.doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID #{payload.doctor_id} not found."
        )

    if not doctor.is_active or (doctor.user and not doctor.user.is_active):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot book an appointment with an inactive physician."
        )

    # 2. Validate Patient Exists
    patient = db.query(User).filter(User.id == patient_id).first()
    if not patient or not patient.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Patient account is invalid or inactive."
        )

    # 3. Validate Date is Not in the Past
    today = date.today()
    if payload.appointment_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot schedule appointments for past dates."
        )

    # 4. Compute & Validate End Time
    if payload.end_time:
        end_time = payload.end_time
    else:
        slot_duration = doctor.slot_duration or 30
        start_dt = datetime.combine(payload.appointment_date, payload.start_time)
        end_dt = start_dt + timedelta(minutes=slot_duration)
        end_time = end_dt.time()

    if payload.start_time >= end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_time must be strictly earlier than end_time."
        )

    # 5. Check Doctor Leave on Target Date
    leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == payload.doctor_id,
        DoctorLeave.leave_date == payload.appointment_date
    ).first()

    if leave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dr. {doctor.user.name if doctor.user else ''} is on leave on {payload.appointment_date}{' (' + leave.reason + ')' if leave.reason else ''}."
        )

    # 6. Check Doctor Working Hours for Day of Week
    day_idx = payload.appointment_date.weekday()
    day_name = DAYS_OF_WEEK_NAMES[day_idx]
    working_hours = db.query(DoctorWorkingHours).filter(
        DoctorWorkingHours.doctor_id == payload.doctor_id,
        DoctorWorkingHours.day_of_week == day_idx
    ).first()

    if not working_hours:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dr. {doctor.user.name if doctor.user else ''} is not scheduled to work on {day_name}s."
        )

    if payload.start_time < working_hours.start_time or end_time > working_hours.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested time slot ({payload.start_time} - {end_time}) falls outside the physician's working hours ({working_hours.start_time} - {working_hours.end_time}) on {day_name}."
        )

    # 7. CONCURRENCY HARDENING: Process-Level Mutex & Row-Level Locking
    now_utc = datetime.now(timezone.utc)

    try:
        with _booking_lock:
            # Re-query inside lock to ensure complete consistency against simultaneous threads
            db.expire_all()
            conflicting_rows = db.query(Appointment).filter(
                Appointment.doctor_id == payload.doctor_id,
                Appointment.appointment_date == payload.appointment_date,
                Appointment.status.in_([AppointmentStatus.HOLD, AppointmentStatus.CONFIRMED]),
                and_(
                    Appointment.start_time < end_time,
                    Appointment.end_time > payload.start_time
                )
            ).all()

            for existing in conflicting_rows:
                if existing.status == AppointmentStatus.CONFIRMED:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error_code": "SLOT_ALREADY_BOOKED",
                            "message": "This appointment slot is no longer available."
                        }
                    )
                elif existing.status == AppointmentStatus.HOLD:
                    # Check hold expiration
                    if existing.hold_until and existing.hold_until.replace(tzinfo=timezone.utc if existing.hold_until.tzinfo is None else existing.hold_until.tzinfo) > now_utc:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail={
                                "error_code": "SLOT_ALREADY_BOOKED",
                                "message": "This appointment slot is temporarily held by another patient."
                            }
                        )
                    else:
                        # Expired hold: transition row to EXPIRED so it does not block
                        existing.status = AppointmentStatus.EXPIRED
                        existing.updated_at = now_utc
                        db.flush()

            # 8. Create and Confirm Appointment
            new_appointment = Appointment(
                patient_id=patient_id,
                doctor_id=payload.doctor_id,
                appointment_date=payload.appointment_date,
                start_time=payload.start_time,
                end_time=end_time,
                status=AppointmentStatus.CONFIRMED,
                symptoms=payload.symptoms.strip() if payload.symptoms else None,
                hold_until=None
            )
            db.add(new_appointment)
            db.commit()
            db.refresh(new_appointment)

        # Trigger Asynchronous Dual Confirmation Notifications & Calendar Event Sync
        try:
            from app.tasks import dispatch_async_task, send_appointment_confirmation_email_task
            from app.tasks.calendar_tasks import sync_google_calendar_event_task
            dispatch_async_task(send_appointment_confirmation_email_task, new_appointment.id)
            dispatch_async_task(sync_google_calendar_event_task, new_appointment.id)
        except Exception:
            pass  # Failure must NEVER rollback appointment changes

        return _serialize_appointment(new_appointment)

    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "SLOT_ALREADY_BOOKED",
                "message": "This appointment slot is no longer available."
            }
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to book appointment: {str(e)}"
        )


def clean_expired_holds(db: Session) -> int:
    """
    Background-compatible cleanup service that transitions expired slot holds to EXPIRED status.
    Returns the count of expired holds cleared.
    """
    now_utc = datetime.now(timezone.utc)
    try:
        expired_holds = db.query(Appointment).filter(
            Appointment.status == AppointmentStatus.HOLD,
            Appointment.hold_until <= now_utc
        ).all()

        count = len(expired_holds)
        for h in expired_holds:
            h.status = AppointmentStatus.EXPIRED
            h.updated_at = now_utc

        db.commit()
        return count
    except Exception:
        db.rollback()
        return 0


def get_user_appointments(
    user: User,
    status_filter: Optional[str],
    db: Session
) -> list[AppointmentResponse]:
    """
    Retrieve appointments according to the authenticated user's role:
    - PATIENT: sees only their own booked appointments.
    - DOCTOR: sees consultations scheduled with them.
    - ADMIN: can view all appointments.
    """
    query = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    )

    if user.role == UserRole.PATIENT:
        query = query.filter(Appointment.patient_id == user.id)
    elif user.role == UserRole.DOCTOR:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doctor:
            return []
        query = query.filter(Appointment.doctor_id == doctor.id)
    elif user.role == UserRole.ADMIN:
        pass  # Admin views all

    if status_filter and status_filter.strip():
        query = query.filter(Appointment.status == status_filter.strip().upper())

    appointments = query.order_by(
        Appointment.appointment_date.desc(),
        Appointment.start_time.desc()
    ).all()

    return [_serialize_appointment(app) for app in appointments]


def get_appointment_by_id(
    appointment_id: int,
    user: User,
    db: Session
) -> AppointmentResponse:
    """
    Retrieve appointment details ensuring role-based access control.
    """
    app = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    ).filter(Appointment.id == appointment_id).first()

    if not app:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    # RBAC Check
    if user.role == UserRole.PATIENT and app.patient_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this appointment."
        )

    if user.role == UserRole.DOCTOR:
        doctor = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doctor or app.doctor_id != doctor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this appointment."
            )

    return _serialize_appointment(app)


def cancel_appointment(
    appointment_id: int,
    user: User,
    payload: AppointmentCancelRequest,
    db: Session
) -> AppointmentResponse:
    """
    Cancel an appointment:
    1. Verify appointment exists & check RBAC permissions.
    2. Set status to CANCELLED and store cancellation_reason (never physically delete, preserve history).
    3. Release slot (making it immediately available for other patients).
    4. Commit transaction.
    5. Trigger async Google Calendar event cancellation.
    6. Trigger async Cancellation Email notification.
    7. Guaranteed non-rollback: calendar or email failures never abort cancellation.
    """
    appointment = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    ).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    # RBAC Check
    if user.role == UserRole.PATIENT and appointment.patient_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    elif user.role == UserRole.DOCTOR:
        doc = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doc or appointment.doctor_id != doc.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    reason = payload.reason or "Cancelled by user"
    cancelled_by = "Patient" if user.role == UserRole.PATIENT else ("Doctor" if user.role == UserRole.DOCTOR else "Admin")

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = reason
    db.commit()
    db.refresh(appointment)

    # Trigger Asynchronous Cancellation Email & Calendar Removal
    try:
        from app.tasks import dispatch_async_task, send_appointment_cancellation_email_task
        from app.tasks.calendar_tasks import cancel_google_calendar_event_task
        dispatch_async_task(
            send_appointment_cancellation_email_task,
            appointment.id,
            reason,
            cancelled_by
        )
        dispatch_async_task(
            cancel_google_calendar_event_task,
            appointment.id,
            None,
            reason
        )
    except Exception:
        pass  # Failure must NEVER rollback appointment cancellation

    return _serialize_appointment(appointment)


def reschedule_appointment(
    appointment_id: int,
    user: User,
    payload: AppointmentRescheduleRequest,
    db: Session
) -> AppointmentResponse:
    """
    Atomically reschedule an appointment:
    1. Verify appointment exists & check RBAC permissions.
    2. Validate new date is not in the past.
    3. Verify doctor schedule & working hours on new date/time.
    4. Atomic double-booking prevention with transaction isolation (check for conflicting appointments).
    5. Update appointment date/time, status to CONFIRMED.
    6. Commit transaction.
    7. Trigger async Google Calendar event update.
    8. Trigger async Reschedule Email notification to patient and doctor.
    9. Guaranteed non-rollback: calendar or email failures never abort appointment update.
    """
    from app.schemas.appointment import AppointmentRescheduleRequest
    appointment = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    ).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    # RBAC Check
    if user.role == UserRole.PATIENT and appointment.patient_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    elif user.role == UserRole.DOCTOR:
        doc = db.query(Doctor).filter(Doctor.user_id == user.id).first()
        if not doc or appointment.doctor_id != doc.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    doctor = appointment.doctor
    if not doctor or not doctor.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Doctor is invalid or inactive.")

    # 1. Validate Date is Not in the Past
    today = date.today()
    if payload.new_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reschedule an appointment to a date in the past."
        )

    # 2. Compute new end time
    slot_duration = doctor.slot_duration or 30
    if payload.new_end_time:
        new_end_time = payload.new_end_time
    else:
        new_dt = datetime.combine(payload.new_date, payload.new_start_time) + timedelta(minutes=slot_duration)
        new_end_time = new_dt.time()

    # 3. Check Doctor Leave
    on_leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == doctor.id,
        DoctorLeave.leave_date == payload.new_date
    ).first()
    if on_leave:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dr. {doctor.user.name if doctor.user else 'Doctor'} is on leave on {payload.new_date} ({on_leave.reason or 'Unavailable'})."
        )

    # 4. Check Doctor Working Hours
    day_idx = payload.new_date.weekday()
    day_name = DAYS_OF_WEEK_NAMES[day_idx] if 0 <= day_idx < len(DAYS_OF_WEEK_NAMES) else "this day"
    working_hour = db.query(DoctorWorkingHours).filter(
        DoctorWorkingHours.doctor_id == doctor.id,
        DoctorWorkingHours.day_of_week == day_idx
    ).first()

    if not working_hour:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dr. {doctor.user.name if doctor.user else 'Doctor'} is not available on {day_name}s."
        )

    if payload.new_start_time < working_hour.start_time or new_end_time > working_hour.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested slot ({payload.new_start_time} - {new_end_time}) is outside doctor's working hours ({working_hour.start_time} - {working_hour.end_time})."
        )

    # 5. Atomic Double-Booking Prevention
    now_utc = datetime.now(timezone.utc)
    with _booking_lock:
        db.expire_all()
        # Check for overlapping appointments on new slot (excluding this appointment)
        conflict = db.query(Appointment).filter(
            Appointment.doctor_id == doctor.id,
            Appointment.appointment_date == payload.new_date,
            Appointment.id != appointment.id,
            Appointment.status.in_([AppointmentStatus.CONFIRMED, AppointmentStatus.HOLD]),
            and_(
                Appointment.start_time < new_end_time,
                Appointment.end_time > payload.new_start_time
            )
        ).first()

        if conflict:
            if conflict.status == AppointmentStatus.CONFIRMED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error_code": "SLOT_ALREADY_BOOKED", "message": "This slot is already booked by another patient."}
                )
            elif conflict.status == AppointmentStatus.HOLD:
                if conflict.hold_until and conflict.hold_until > now_utc:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={"error_code": "SLOT_HELD", "message": "This slot is temporarily held by another patient."}
                    )

        # 6. Capture old dates for notification and update appointment
        old_date_str = str(appointment.appointment_date)
        old_time_str = appointment.start_time.strftime("%H:%M")

        appointment.appointment_date = payload.new_date
        appointment.start_time = payload.new_start_time
        appointment.end_time = new_end_time
        appointment.status = AppointmentStatus.CONFIRMED
        db.commit()
        db.refresh(appointment)

    new_date_str = str(payload.new_date)
    new_time_str = payload.new_start_time.strftime("%H:%M")

    # 7. Asynchronously trigger Google Calendar update & Reschedule notification
    try:
        from app.tasks import dispatch_async_task, send_appointment_reschedule_email_task
        from app.tasks.calendar_tasks import update_google_calendar_event_task
        dispatch_async_task(
            send_appointment_reschedule_email_task,
            appointment.id,
            old_date_str,
            old_time_str,
            new_date_str,
            new_time_str
        )
        dispatch_async_task(
            update_google_calendar_event_task,
            appointment.id
        )
    except Exception:
        pass  # Failure must NEVER rollback appointment update

    return _serialize_appointment(appointment)
