from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.prescription import (
    ConsultationSubmitRequest,
    PrescriptionCreateRequest,
    PrescriptionResponse,
)
from app.services.prescription_service import (
    submit_consultation,
    create_prescription,
    get_appointment_prescription,
)
from app.utils.dependencies import get_current_user

router = APIRouter(prefix="/appointments", tags=["Doctor Post-Visit Consultations & Prescriptions"])


@router.post(
    "/{appointment_id}/consultation",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Doctor: Submit Consultation Clinical Notes"
)
def submit_appointment_consultation(
    appointment_id: int,
    payload: ConsultationSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit clinical notes for an appointment and transition status to COMPLETED.
    Only the assigned doctor (or admin) can execute this action.
    """
    return submit_consultation(
        appointment_id=appointment_id,
        current_user=current_user,
        notes=payload.notes,
        follow_up_instructions=payload.follow_up_instructions,
        db=db
    )


@router.post(
    "/{appointment_id}/prescription",
    response_model=PrescriptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Doctor: Issue Clinical Prescription with Medications"
)
def submit_appointment_prescription(
    appointment_id: int,
    payload: PrescriptionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit or update a clinical prescription with medication items, dosage, frequency, and duration.
    Transitions appointment status to COMPLETED.
    Only the assigned doctor (or admin) can execute this action.
    """
    return create_prescription(
        appointment_id=appointment_id,
        current_user=current_user,
        notes=payload.notes,
        follow_up_instructions=payload.follow_up_instructions,
        medications=payload.medications,
        db=db
    )


@router.get(
    "/{appointment_id}/prescription",
    response_model=PrescriptionResponse,
    summary="Get Clinical Prescription"
)
def fetch_appointment_prescription(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve the clinical prescription record and prescribed medications for an appointment.
    Accessible by the patient owner, assigned doctor, or admin.
    """
    return get_appointment_prescription(
        appointment_id=appointment_id,
        current_user=current_user,
        db=db
    )
