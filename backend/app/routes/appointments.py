from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.dependencies import get_current_user
from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentResponse,
    AppointmentCancelRequest,
    AppointmentRescheduleRequest,
)
from app.services.appointment_service import (
    book_appointment,
    get_user_appointments,
    get_appointment_by_id,
)

router = APIRouter(prefix="/appointments", tags=["Appointments"])


@router.post(
    "",
    response_model=AppointmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Book an Appointment"
)
def create_appointment_endpoint(
    payload: AppointmentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Book a consultation slot with a doctor.
    Enforces that the physician is active, working that day, not on leave,
    and that the requested time slot is not already booked.
    """
    return book_appointment(patient_id=current_user.id, payload=payload, db=db)


@router.get(
    "",
    response_model=list[AppointmentResponse],
    summary="List Appointments"
)
def list_appointments_endpoint(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by appointment status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve appointments according to the authenticated user's role:
    - Patients view their own booked appointments.
    - Doctors view consultations booked with them.
    - Admins view all appointments.
    """
    return get_user_appointments(user=current_user, status_filter=status_filter, db=db)


@router.get(
    "/{appointment_id}",
    response_model=AppointmentResponse,
    summary="Get Appointment Details"
)
def get_appointment_details_endpoint(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve details for a specific appointment ID.
    Enforces role-based ownership checks.
    """
    return get_appointment_by_id(appointment_id=appointment_id, user=current_user, db=db)


@router.post(
    "/cleanup-expired-holds",
    summary="Cleanup Expired Slot Holds"
)
def cleanup_expired_holds_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Background-compatible maintenance endpoint to release expired slot holds.
    """
    from app.services.appointment_service import clean_expired_holds
    cleared = clean_expired_holds(db=db)
    return {
        "success": True,
        "cleared_count": cleared,
        "message": f"Successfully cleared {cleared} expired hold(s)."
    }


@router.get(
    "/{appointment_id}/calendar-invite",
    summary="Download iCalendar (.ics) Invite"
)
def download_calendar_invite_endpoint(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download RFC 5545 compliant .ics calendar invite for the appointment.
    """
    from fastapi.responses import Response
    from fastapi import HTTPException
    from app.models.appointment import Appointment
    from app.models.doctor import Doctor
    from app.tasks.calendar_tasks import generate_ical_content

    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # RBAC ownership check
    if current_user.role == "PATIENT" and appointment.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif current_user.role == "DOCTOR":
        doc = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if not doc or appointment.doctor_id != doc.id:
            raise HTTPException(status_code=403, detail="Forbidden")

    ical_text = generate_ical_content(appointment)
    return Response(
        content=ical_text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="caresync-appointment-{appointment.id}.ics"'
        }
    )


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    summary="Cancel an Appointment"
)
@router.patch(
    "/{appointment_id}/cancel",
    response_model=AppointmentResponse,
    summary="Cancel an Appointment (Patch)"
)
def cancel_appointment_endpoint(
    appointment_id: int,
    payload: AppointmentCancelRequest = AppointmentCancelRequest(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Cancel an appointment and notify both Patient and Doctor asynchronously.
    """
    from app.services.appointment_service import cancel_appointment
    return cancel_appointment(appointment_id=appointment_id, user=current_user, payload=payload, db=db)


@router.post(
    "/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    summary="Reschedule an Appointment"
)
@router.patch(
    "/{appointment_id}/reschedule",
    response_model=AppointmentResponse,
    summary="Reschedule an Appointment (Patch)"
)
def reschedule_appointment_endpoint(
    appointment_id: int,
    payload: AppointmentRescheduleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reschedule an appointment slot and notify both Patient and Doctor.
    """
    from app.services.appointment_service import reschedule_appointment
    return reschedule_appointment(appointment_id=appointment_id, user=current_user, payload=payload, db=db)




