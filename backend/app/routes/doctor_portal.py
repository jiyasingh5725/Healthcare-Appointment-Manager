from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User
from app.models.doctor import Doctor
from app.models.appointment import Appointment, AppointmentStatus
from app.utils.dependencies import require_doctor
from app.schemas.doctor import (
    DoctorResponse,
    DoctorProfileUpdateRequest,
    DoctorAppointmentStatusUpdateRequest,
)
from app.schemas.appointment import AppointmentResponse
from app.services.appointment_service import _serialize_appointment

router = APIRouter(prefix="/doctor", tags=["Doctor Portal"])


@router.get(
    "/profile",
    response_model=DoctorResponse,
    summary="Get Authenticated Doctor Profile"
)
def get_doctor_profile(
    current_user: User = Depends(require_doctor),
    db: Session = Depends(get_db)
):
    """
    Retrieve clinical profile details for the authenticated doctor.
    """
    doctor = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.user_id == current_user.id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found."
        )

    return DoctorResponse(
        id=doctor.id,
        user_id=doctor.user_id,
        name=doctor.user.name,
        email=doctor.user.email,
        phone=doctor.user.phone,
        specialization=doctor.specialization,
        qualification=doctor.qualification,
        experience=doctor.experience,
        slot_duration=doctor.slot_duration,
        is_active=doctor.is_active,
        created_at=doctor.created_at,
        updated_at=doctor.updated_at,
    )


@router.put(
    "/profile",
    response_model=DoctorResponse,
    summary="Update Doctor Profile & Credentials"
)
def update_doctor_profile(
    payload: DoctorProfileUpdateRequest,
    current_user: User = Depends(require_doctor),
    db: Session = Depends(get_db)
):
    """
    Update clinical profile and credentials for the authenticated doctor.
    """
    doctor = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.user_id == current_user.id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found."
        )

    if payload.name is not None and payload.name.strip():
        current_user.name = payload.name.strip()
    if payload.phone is not None:
        current_user.phone = payload.phone.strip() if payload.phone.strip() else None

    if payload.specialization is not None and payload.specialization.strip():
        doctor.specialization = payload.specialization.strip()
    if payload.qualification is not None:
        doctor.qualification = payload.qualification.strip() if payload.qualification.strip() else None
    if payload.experience is not None:
        doctor.experience = payload.experience
    if payload.slot_duration is not None:
        doctor.slot_duration = payload.slot_duration

    db.commit()
    db.refresh(doctor)
    db.refresh(current_user)

    return DoctorResponse(
        id=doctor.id,
        user_id=doctor.user_id,
        name=doctor.user.name,
        email=doctor.user.email,
        phone=doctor.user.phone,
        specialization=doctor.specialization,
        qualification=doctor.qualification,
        experience=doctor.experience,
        slot_duration=doctor.slot_duration,
        is_active=doctor.is_active,
        created_at=doctor.created_at,
        updated_at=doctor.updated_at,
    )


@router.patch(
    "/appointments/{appointment_id}/status",
    response_model=AppointmentResponse,
    summary="Update Appointment Status by Doctor"
)
def update_appointment_status_by_doctor(
    appointment_id: int,
    payload: DoctorAppointmentStatusUpdateRequest,
    current_user: User = Depends(require_doctor),
    db: Session = Depends(get_db)
):
    """
    Update appointment status (e.g. COMPLETED, CANCELLED).
    Enforces strict privacy: only the assigned doctor can modify the status.
    """
    doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor profile not found."
        )

    appointment = db.query(Appointment).options(
        joinedload(Appointment.patient),
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    ).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    if appointment.doctor_id != doctor.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify another physician's appointment."
        )

    # Validate status enum
    try:
        new_status = AppointmentStatus(payload.status.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{payload.status}'. Valid statuses: {[s.value for s in AppointmentStatus]}"
        )

    appointment.status = new_status
    if payload.cancellation_reason:
        appointment.cancellation_reason = payload.cancellation_reason

    db.commit()
    db.refresh(appointment)

    return _serialize_appointment(appointment)
