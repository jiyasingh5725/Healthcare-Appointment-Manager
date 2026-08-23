import logging
from datetime import datetime, date, timezone
from typing import Optional, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User, UserRole
from app.models.appointment import Appointment, AppointmentStatus
from app.models.prescription import Prescription, Medication
from app.models.doctor import Doctor
from app.models.notification import Notification, NotificationType
from app.utils.dependencies import get_current_user, require_role
from app.tasks.reminder_tasks import (
    parse_medication_frequency,
    compute_next_dose_time,
    send_appointment_reminder_task,
    send_medication_reminder_task,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patient", tags=["Patient Portal & Reminders"])


@router.get(
    "/medications",
    summary="Patient: List Active Prescribed Medications & Reminders"
)
def get_patient_medications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Retrieve all prescribed medications for the logged-in patient with frequency parsing,
    calculated next dose times, and reminder status.
    """
    # Verify patient ownership (or allow admin review)
    patient_id = current_user.id

    # Query prescriptions for this patient
    prescriptions = db.query(Prescription).options(
        joinedload(Prescription.medications),
        joinedload(Prescription.doctor).joinedload(Doctor.user),
        joinedload(Prescription.appointment)
    ).filter(
        Prescription.patient_id == patient_id
    ).order_by(Prescription.created_at.desc()).all()

    medications_list = []
    now_utc = datetime.now(timezone.utc)

    for p in prescriptions:
        doctor_name = p.doctor.user.name if (p.doctor and p.doctor.user) else "Physician"
        appointment_date = str(p.appointment.appointment_date) if p.appointment else ""

        for m in p.medications:
            parsed_freq = parse_medication_frequency(m.frequency)
            next_dose = compute_next_dose_time(m.frequency, current_dt=now_utc)

            medications_list.append({
                "id": m.id,
                "prescription_id": p.id,
                "medication_name": m.medication_name,
                "dosage": m.dosage,
                "frequency": m.frequency,
                "duration": m.duration,
                "instructions": m.instructions or "As directed by physician",
                "reminder_enabled": m.reminder_enabled,
                "doctor_name": doctor_name,
                "prescribed_date": appointment_date or (m.created_at.strftime("%Y-%m-%d") if m.created_at else ""),
                "frequency_info": parsed_freq,
                "next_dose_time": next_dose.isoformat() if next_dose else None,
                "next_dose_display": next_dose.strftime("%A at %I:%M %p") if next_dose else "Scheduled",
            })

    return {
        "success": True,
        "total_medications": len(medications_list),
        "medications": medications_list
    }


@router.patch(
    "/medications/{medication_id}/toggle-reminder",
    summary="Patient: Toggle Medication Reminder Status"
)
def toggle_medication_reminder(
    medication_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Toggle or update reminder_enabled state for a patient's medication.
    """
    med = db.query(Medication).options(
        joinedload(Medication.prescription)
    ).filter(Medication.id == medication_id).first()

    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Medication #{medication_id} not found."
        )

    # Ownership check
    if med.prescription.patient_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this medication reminder."
        )

    # Toggle reminder_enabled state safely
    current_status = bool(getattr(med, "reminder_enabled", True))
    setattr(med, "reminder_enabled", not current_status)
    db.commit()
    db.refresh(med)

    new_status = bool(getattr(med, "reminder_enabled", True))
    return {
        "success": True,
        "medication_id": med.id,
        "medication_name": med.medication_name,
        "reminder_enabled": new_status,
        "message": f"Reminders {'enabled' if new_status else 'disabled'} for {med.medication_name}."
    }


@router.get(
    "/reminders/upcoming",
    summary="Patient: Aggregated Upcoming Appointment & Medication Reminders"
)
def get_upcoming_reminders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Aggregated view of upcoming appointment reminders and medication schedules for patient dashboard.
    """
    patient_id = current_user.id
    today = date.today()
    now_utc = datetime.now(timezone.utc)

    # 1. Upcoming confirmed appointments
    upcoming_appointments = db.query(Appointment).options(
        joinedload(Appointment.doctor).joinedload(Doctor.user)
    ).filter(
        Appointment.patient_id == patient_id,
        Appointment.status == AppointmentStatus.CONFIRMED,
        Appointment.appointment_date >= today
    ).order_by(Appointment.appointment_date.asc(), Appointment.start_time.asc()).limit(5).all()

    appointment_reminders = []
    for app in upcoming_appointments:
        doc_name = app.doctor.user.name if (app.doctor and app.doctor.user) else "Physician"
        appointment_reminders.append({
            "appointment_id": app.id,
            "doctor_name": doc_name,
            "specialization": app.doctor.specialization if app.doctor else "",
            "date": str(app.appointment_date),
            "start_time": str(app.start_time),
            "status": app.status.value,
            "reminders": {
                "24h_window": "Active",
                "1h_window": "Active"
            }
        })

    # 2. Active prescribed medications
    prescriptions = db.query(Prescription).options(
        joinedload(Prescription.medications)
    ).filter(
        Prescription.patient_id == patient_id
    ).all()

    medication_schedules = []
    for p in prescriptions:
        for m in p.medications:
            if m.reminder_enabled:
                next_dose = compute_next_dose_time(m.frequency, current_dt=now_utc)
                medication_schedules.append({
                    "medication_id": m.id,
                    "name": m.medication_name,
                    "dosage": m.dosage,
                    "frequency": m.frequency,
                    "next_dose_time": next_dose.isoformat() if next_dose else None,
                    "next_dose_display": next_dose.strftime("%A at %I:%M %p") if next_dose else "Scheduled",
                    "reminder_enabled": m.reminder_enabled
                })

    # Sort medication schedules by next dose
    medication_schedules.sort(key=lambda x: x.get("next_dose_time") or "")

    return {
        "success": True,
        "upcoming_appointments": appointment_reminders,
        "upcoming_medications": medication_schedules
    }


@router.post(
    "/reminders/trigger-now",
    summary="Patient: Manually Trigger/Test Reminder Dispatch"
)
def trigger_reminder_now(
    target_type: str = Query(..., description="Type of reminder: 'appointment' or 'medication'"),
    target_id: int = Query(..., description="Appointment ID or Medication ID"),
    window: Optional[str] = Query("24h", description="Window for appointment reminder: '24h' or '1h'"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Diagnostic / testing endpoint allowing patient or admin to trigger a background reminder job immediately.
    """
    if target_type.lower() == "appointment":
        app = db.query(Appointment).filter(Appointment.id == target_id).first()
        if not app:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if app.patient_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Forbidden")

        res = send_appointment_reminder_task(appointment_id=target_id, window_label=window)
        return {"success": True, "result": res}

    elif target_type.lower() == "medication":
        med = db.query(Medication).options(joinedload(Medication.prescription)).filter(Medication.id == target_id).first()
        if not med:
            raise HTTPException(status_code=404, detail="Medication not found")
        if med.prescription.patient_id != current_user.id and current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Forbidden")

        res = send_medication_reminder_task(medication_id=target_id)
        return {"success": True, "result": res}

    else:
        raise HTTPException(status_code=400, detail="Invalid target_type. Use 'appointment' or 'medication'.")
