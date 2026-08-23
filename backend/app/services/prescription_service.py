import logging
from typing import Optional, Any
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.models.doctor import Doctor
from app.models.appointment import Appointment, AppointmentStatus
from app.models.prescription import Prescription, Medication
from app.schemas.prescription import MedicationItem

logger = logging.getLogger(__name__)


def _verify_doctor_access(appointment: Appointment, current_user: User, db: Session):
    """Ensure only the assigned doctor or admin can write/submit consultation and prescriptions."""
    if current_user.role == UserRole.ADMIN:
        return
    if current_user.role == UserRole.DOCTOR:
        doctor = db.query(Doctor).filter(Doctor.user_id == current_user.id).first()
        if doctor and appointment.doctor_id == doctor.id:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit consultations and prescriptions for your own assigned appointments."
        )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Only physicians can submit clinical consultation notes and prescriptions."
    )


def _verify_read_access(appointment: Appointment, current_user: User, db: Session):
    """Ensure only patient owner, assigned doctor, or admin can read prescriptions."""
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
        detail="You do not have permission to view the clinical prescription for this appointment."
    )


def _serialize_prescription(prescription: Prescription) -> dict[str, Any]:
    """Serialize Prescription ORM entity to dict format."""
    doctor_name = "Unknown"
    doctor_spec = "General Practice"
    if prescription.doctor:
        doctor_spec = prescription.doctor.specialization
        if prescription.doctor.user:
            doctor_name = prescription.doctor.user.name

    patient_name = prescription.patient.name if prescription.patient else "Patient"
    patient_email = prescription.patient.email if prescription.patient else ""

    meds_list = []
    if prescription.medications:
        for m in prescription.medications:
            meds_list.append({
                "id": m.id,
                "prescription_id": m.prescription_id,
                "medication_name": m.medication_name,
                "dosage": m.dosage,
                "frequency": m.frequency,
                "duration": m.duration,
                "instructions": m.instructions,
                "reminder_enabled": m.reminder_enabled,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            })

    return {
        "id": prescription.id,
        "appointment_id": prescription.appointment_id,
        "doctor_id": prescription.doctor_id,
        "doctor_name": doctor_name,
        "doctor_specialization": doctor_spec,
        "patient_id": prescription.patient_id,
        "patient_name": patient_name,
        "patient_email": patient_email,
        "notes": prescription.notes,
        "follow_up_instructions": prescription.follow_up_instructions,
        "medications": meds_list,
        "created_at": prescription.created_at,
        "updated_at": prescription.updated_at,
    }


def submit_consultation(
    appointment_id: int,
    current_user: User,
    notes: Optional[str],
    follow_up_instructions: Optional[str],
    db: Session
) -> dict[str, Any]:
    """
    Submit clinical notes and mark appointment as COMPLETED.
    """
    appointment = db.query(Appointment).options(
        joinedload(Appointment.doctor).joinedload(Doctor.user),
        joinedload(Appointment.patient)
    ).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_doctor_access(appointment, current_user, db)

    prescription = db.query(Prescription).filter(Prescription.appointment_id == appointment_id).first()
    if prescription:
        prescription.notes = notes
        prescription.follow_up_instructions = follow_up_instructions
    else:
        prescription = Prescription(
            appointment_id=appointment.id,
            doctor_id=appointment.doctor_id,
            patient_id=appointment.patient_id,
            notes=notes,
            follow_up_instructions=follow_up_instructions
        )
        db.add(prescription)

    # Transition status to COMPLETED
    appointment.status = AppointmentStatus.COMPLETED
    db.commit()
    db.refresh(prescription)

    # Trigger Asynchronous Post-Visit Patient Care Email and Doctor Completion Confirmation
    try:
        from app.tasks import dispatch_async_task, send_appointment_completed_notifications_task
        dispatch_async_task(send_appointment_completed_notifications_task, appointment.id)
    except Exception as e:
        logger.warning(f"[PrescriptionService] Non-blocking completion notification dispatch failed: {e}")

    return _serialize_prescription(prescription)


def create_prescription(
    appointment_id: int,
    current_user: User,
    notes: Optional[str],
    follow_up_instructions: Optional[str],
    medications: list[MedicationItem],
    db: Session
) -> dict[str, Any]:
    """
    Create or update full clinical prescription with medications and mark appointment as COMPLETED.
    """
    appointment = db.query(Appointment).options(
        joinedload(Appointment.doctor).joinedload(Doctor.user),
        joinedload(Appointment.patient)
    ).filter(Appointment.id == appointment_id).first()

    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_doctor_access(appointment, current_user, db)

    prescription = db.query(Prescription).filter(Prescription.appointment_id == appointment_id).first()
    if not prescription:
        prescription = Prescription(
            appointment_id=appointment.id,
            doctor_id=appointment.doctor_id,
            patient_id=appointment.patient_id,
            notes=notes,
            follow_up_instructions=follow_up_instructions
        )
        db.add(prescription)
        db.flush()
    else:
        prescription.notes = notes
        prescription.follow_up_instructions = follow_up_instructions
        # Clear existing medications to replace with new set
        db.query(Medication).filter(Medication.prescription_id == prescription.id).delete()

    # Add medication items
    for med in medications:
        new_med = Medication(
            prescription_id=prescription.id,
            medication_name=med.medication_name.strip(),
            dosage=med.dosage.strip(),
            frequency=med.frequency.strip(),
            duration=med.duration.strip(),
            instructions=med.instructions.strip() if med.instructions else None,
            reminder_enabled=med.reminder_enabled
        )
        db.add(new_med)

    # Mark appointment as COMPLETED
    appointment.status = AppointmentStatus.COMPLETED
    db.commit()
    db.refresh(prescription)

    # Trigger Asynchronous Post-Visit Patient Care Email and Doctor Completion Confirmation
    try:
        from app.tasks import dispatch_async_task, send_appointment_completed_notifications_task
        dispatch_async_task(send_appointment_completed_notifications_task, appointment.id)
    except Exception as e:
        logger.warning(f"[PrescriptionService] Non-blocking completion notification dispatch failed: {e}")

    return _serialize_prescription(prescription)


def get_appointment_prescription(
    appointment_id: int,
    current_user: User,
    db: Session
) -> dict[str, Any]:
    """
    Retrieve clinical prescription record for an appointment.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    _verify_read_access(appointment, current_user, db)

    prescription = db.query(Prescription).options(
        joinedload(Prescription.doctor).joinedload(Doctor.user),
        joinedload(Prescription.patient),
        joinedload(Prescription.medications)
    ).filter(Prescription.appointment_id == appointment_id).first()

    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No prescription has been issued yet for appointment #{appointment_id}."
        )

    return _serialize_prescription(prescription)
