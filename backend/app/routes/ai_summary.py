from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.user import User, UserRole
from app.models.doctor import Doctor
from app.models.appointment import Appointment
from app.schemas.ai_summary import (
    PrevisitSummaryRequest,
    PrevisitSummaryResponse,
    PostvisitSummaryRequest,
    PostvisitSummaryResponse,
)
from app.services.ai_summary_service import (
    generate_previsit_summary,
    get_previsit_summary,
    generate_postvisit_summary,
    get_postvisit_summary,
)
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/appointments", tags=["AI Clinical Summaries"])


def _verify_appointment_access(appointment: Appointment, current_user: User, db: Session):
    """Ensure user has permission to access or generate AI summary for this appointment."""
    if current_user.role == UserRole.ADMIN:
        return
    if current_user.role == UserRole.PATIENT and appointment.patient_id == current_user.id:
        return
    if current_user.role == UserRole.DOCTOR:
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if doctor and appointment.doctor_id == doctor.id:
            return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access the clinical summary for this appointment."
    )


@router.post(
    "/{appointment_id}/previsit-summary",
    response_model=PrevisitSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Pre-visit AI Symptom Summary"
)
def create_previsit_summary(
    appointment_id: int,
    payload: Optional[PrevisitSummaryRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate or refresh pre-visit AI symptom summary for an appointment.
    Non-diagnostic decision-support feature with graceful fallback handling.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_appointment_access(appointment, current_user, db)

    symptoms_override = payload.symptoms if payload else None
    result = generate_previsit_summary(
        appointment_id=appointment_id,
        symptoms_override=symptoms_override,
        db=db
    )
    return result


@router.get(
    "/{appointment_id}/previsit-summary",
    response_model=PrevisitSummaryResponse,
    summary="Get Existing Pre-visit AI Symptom Summary"
)
def fetch_previsit_summary(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve an existing pre-visit AI symptom summary for an appointment.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_appointment_access(appointment, current_user, db)

    summary = get_previsit_summary(appointment_id=appointment_id, db=db)
    if not summary:
        summary = generate_previsit_summary(
            appointment_id=appointment_id,
            symptoms_override=None,
            db=db
        )
    return summary


# ==========================================
# PHASE 14: POST-VISIT SUMMARY ENDPOINTS
# ==========================================

@router.post(
    "/{appointment_id}/postvisit-summary",
    response_model=PostvisitSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate Patient-Friendly Post-Visit AI Summary"
)
def create_postvisit_summary(
    appointment_id: int,
    payload: Optional[PostvisitSummaryRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate or refresh a patient-friendly post-visit AI care summary from physician notes & prescription.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_appointment_access(appointment, current_user, db)

    notes_override = payload.notes_override if payload else None
    return generate_postvisit_summary(
        appointment_id=appointment_id,
        notes_override=notes_override,
        db=db
    )


@router.get(
    "/{appointment_id}/postvisit-summary",
    response_model=PostvisitSummaryResponse,
    summary="Get Patient-Friendly Post-Visit AI Summary"
)
def fetch_postvisit_summary(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve existing patient-friendly post-visit AI summary for an appointment.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_appointment_access(appointment, current_user, db)

    summary = get_postvisit_summary(appointment_id=appointment_id, db=db)
    if not summary:
        # Generate automatically on-demand
        summary = generate_postvisit_summary(
            appointment_id=appointment_id,
            notes_override=None,
            db=db
        )
    return summary

