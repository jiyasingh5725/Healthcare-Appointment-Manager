from datetime import date, time
from typing import Optional, Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import inspect

from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorWorkingHours, DoctorLeave
from app.schemas.doctor_schedule import (
    WorkingHoursItem,
    WorkingHoursResponse,
    DoctorLeaveResponse,
    DoctorLeaveWithConflictsResponse,
    DAYS_OF_WEEK_NAMES,
)


def _ensure_doctor_exists(doctor_id: int, db: Session) -> Doctor:
    """Verify that the specified doctor exists in the database."""
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID #{doctor_id} not found."
        )
    return doctor


def get_doctor_working_hours(doctor_id: int, db: Session) -> list[WorkingHoursResponse]:
    """
    Retrieve full 7-day weekly working hours configuration for a doctor.
    Returns days 0 (Monday) through 6 (Sunday).
    """
    _ensure_doctor_exists(doctor_id, db)

    # Fetch configured hours
    existing_hours = db.query(DoctorWorkingHours).filter(
        DoctorWorkingHours.doctor_id == doctor_id
    ).all()

    hours_map = {wh.day_of_week: wh for wh in existing_hours}

    result = []
    for day_idx in range(7):
        day_name = DAYS_OF_WEEK_NAMES[day_idx]
        wh = hours_map.get(day_idx)

        if wh:
            result.append(
                WorkingHoursResponse(
                    id=wh.id,
                    doctor_id=doctor_id,
                    day_of_week=day_idx,
                    day_name=day_name,
                    start_time=wh.start_time,
                    end_time=wh.end_time,
                    is_working=True,
                )
            )
        else:
            result.append(
                WorkingHoursResponse(
                    id=None,
                    doctor_id=doctor_id,
                    day_of_week=day_idx,
                    day_name=day_name,
                    start_time=None,
                    end_time=None,
                    is_working=False,
                )
            )

    return result


def update_doctor_working_hours(
    doctor_id: int,
    items: list[WorkingHoursItem],
    db: Session
) -> list[WorkingHoursResponse]:
    """
    Update or replace working hours for a doctor across the week.
    Executed in an atomic database transaction.
    """
    _ensure_doctor_exists(doctor_id, db)

    # Validate all items
    for item in items:
        if item.is_working:
            if item.start_time >= item.end_time:
                day_name = DAYS_OF_WEEK_NAMES[item.day_of_week]
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid working hours for {day_name}: start_time ({item.start_time}) must be earlier than end_time ({item.end_time})."
                )

    try:
        # Remove existing working hours for this doctor
        db.query(DoctorWorkingHours).filter(
            DoctorWorkingHours.doctor_id == doctor_id
        ).delete(synchronize_session=False)

        # Insert new active working hours
        for item in items:
            if item.is_working:
                new_wh = DoctorWorkingHours(
                    doctor_id=doctor_id,
                    day_of_week=item.day_of_week,
                    start_time=item.start_time,
                    end_time=item.end_time,
                )
                db.add(new_wh)

        db.commit()
        return get_doctor_working_hours(doctor_id, db)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update working hours: {str(e)}"
        )


def detect_appointment_conflicts(doctor_id: int, target_date: date, db: Session) -> list[dict[str, Any]]:
    """
    Check for existing appointments scheduled on target_date for doctor_id.
    Safely inspects if appointments table exists (preserving compatibility before appointment model creation).
    Preserves all appointment records without deletion.
    """
    conflicts: list[dict[str, Any]] = []

    # Check if appointments table exists in database
    inspector = inspect(db.bind)
    if "appointments" in inspector.get_table_names():
        try:
            # Query appointments for doctor on target date
            from sqlalchemy import text
            stmt = text("""
                SELECT id, patient_id, appointment_time, status 
                FROM appointments 
                WHERE doctor_id = :doc_id 
                  AND DATE(appointment_time) = :target_date 
                  AND status NOT IN ('CANCELLED', 'REJECTED')
            """)
            rows = db.execute(stmt, {"doc_id": doctor_id, "target_date": target_date}).fetchall()
            for row in rows:
                conflicts.append({
                    "appointment_id": row[0],
                    "patient_id": row[1],
                    "appointment_time": str(row[2]),
                    "status": row[3]
                })
        except Exception:
            # Safe fallback if schema is evolving
            pass

    return conflicts


def get_doctor_leaves(doctor_id: int, upcoming_only: bool, db: Session) -> list[DoctorLeaveResponse]:
    """
    Retrieve all scheduled leaves for a doctor.
    """
    _ensure_doctor_exists(doctor_id, db)

    query = db.query(DoctorLeave).filter(DoctorLeave.doctor_id == doctor_id)
    if upcoming_only:
        query = query.filter(DoctorLeave.leave_date >= date.today())

    leaves = query.order_by(DoctorLeave.leave_date.asc()).all()
    return [DoctorLeaveResponse.model_validate(l) for l in leaves]


def create_doctor_leave(
    doctor_id: int,
    leave_date: date,
    reason: Optional[str],
    db: Session
) -> DoctorLeaveWithConflictsResponse:
    """
    Schedule a leave for a doctor.
    Validates date, prevents duplicates, detects appointment conflicts, and preserves history.
    """
    _ensure_doctor_exists(doctor_id, db)

    # 1. Validate date is not in the past
    today = date.today()
    if leave_date < today:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot schedule leave for a past date ({leave_date}). Please select today or a future date."
        )

    # 2. Check for duplicate leave on the same date
    existing_leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == doctor_id,
        DoctorLeave.leave_date == leave_date
    ).first()

    if existing_leave:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A leave is already scheduled for this doctor on {leave_date}."
        )

    # 3. Detect conflicting appointments (preserves history, does not delete)
    conflicts = detect_appointment_conflicts(doctor_id, leave_date, db)

    # Fetch doctor name for notification messages
    doctor = _ensure_doctor_exists(doctor_id, db)
    doctor_name = doctor.user.name if (doctor and doctor.user) else f"Doctor #{doctor_id}"

    try:
        new_leave = DoctorLeave(
            doctor_id=doctor_id,
            leave_date=leave_date,
            reason=reason.strip() if reason else None
        )
        db.add(new_leave)
        db.commit()
        db.refresh(new_leave)

        # Process leave conflicts: cancel appointments, create notifications, prepare email/calendar sync jobs
        from app.services.leave_conflict_service import process_leave_conflicts
        conflict_data = process_leave_conflicts(
            doctor_id=doctor_id,
            leave_date=leave_date,
            doctor_name=doctor_name,
            db=db
        )

        affected_count = conflict_data["affected_appointments_count"]
        message = (
            f"Leave scheduled for {leave_date}. {affected_count} existing appointment(s) automatically cancelled and patient notification jobs prepared."
            if affected_count > 0
            else f"Leave scheduled successfully for {leave_date}."
        )

        return DoctorLeaveWithConflictsResponse(
            leave=DoctorLeaveResponse.model_validate(new_leave),
            affected_appointments_count=affected_count,
            affected_appointments=conflict_data["affected_appointments"],
            patients_to_notify=conflict_data["patients_to_notify"],
            notifications_prepared=conflict_data["notifications_prepared"],
            calendar_sync_jobs_prepared=conflict_data["calendar_sync_jobs_prepared"],
            conflicting_appointments_count=affected_count,
            conflicts=conflict_data["affected_appointments"],
            message=message
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create doctor leave: {str(e)}"
        )


def delete_doctor_leave(doctor_id: int, leave_id: int, db: Session) -> dict[str, Any]:
    """
    Cancel / delete a doctor leave record.
    """
    _ensure_doctor_exists(doctor_id, db)

    leave = db.query(DoctorLeave).filter(
        DoctorLeave.id == leave_id,
        DoctorLeave.doctor_id == doctor_id
    ).first()

    if not leave:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Leave record #{leave_id} for Doctor #{doctor_id} not found."
        )

    try:
        db.delete(leave)
        db.commit()
        return {
            "success": True,
            "message": f"Leave on {leave.leave_date} deleted successfully."
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete leave: {str(e)}"
        )
