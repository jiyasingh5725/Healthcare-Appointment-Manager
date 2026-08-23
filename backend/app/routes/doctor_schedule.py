from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.utils.dependencies import require_admin
from app.schemas.doctor_schedule import (
    WorkingHoursBulkUpdateRequest,
    WorkingHoursResponse,
    DoctorLeaveCreateRequest,
    DoctorLeaveResponse,
    DoctorLeaveWithConflictsResponse,
)
from app.services.doctor_schedule_service import (
    get_doctor_working_hours,
    update_doctor_working_hours,
    get_doctor_leaves,
    create_doctor_leave,
    delete_doctor_leave,
)

router = APIRouter(prefix="/admin/doctors/{doctor_id}", tags=["Admin Doctor Schedules & Leaves"])


# --- Working Hours Endpoints ---

@router.get(
    "/working-hours",
    response_model=list[WorkingHoursResponse],
    summary="Admin: Get Doctor Weekly Working Hours"
)
def get_working_hours_endpoint(
    doctor_id: int,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieve working hours configuration for Monday through Sunday for a doctor.
    """
    return get_doctor_working_hours(doctor_id, db)


@router.put(
    "/working-hours",
    response_model=list[WorkingHoursResponse],
    summary="Admin: Configure Doctor Weekly Working Hours"
)
def update_working_hours_endpoint(
    doctor_id: int,
    payload: WorkingHoursBulkUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Configure or update working hours for Monday through Sunday for a doctor.
    """
    return update_doctor_working_hours(doctor_id, payload.working_hours, db)


# --- Doctor Leave Endpoints ---

@router.get(
    "/leaves",
    response_model=list[DoctorLeaveResponse],
    summary="Admin: Get Doctor Leaves"
)
def get_doctor_leaves_endpoint(
    doctor_id: int,
    upcoming_only: bool = Query(False, description="Filter for upcoming leaves only"),
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieve scheduled leaves for a doctor.
    """
    return get_doctor_leaves(doctor_id, upcoming_only, db)


@router.post(
    "/leaves",
    response_model=DoctorLeaveWithConflictsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: Schedule Doctor Leave"
)
def create_doctor_leave_endpoint(
    doctor_id: int,
    payload: DoctorLeaveCreateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Schedule a leave date for a doctor.
    Detects any existing conflicting appointments without deleting them to preserve medical records.
    """
    return create_doctor_leave(doctor_id, payload.leave_date, payload.reason, db)


@router.delete(
    "/leaves/{leave_id}",
    summary="Admin: Delete / Cancel Doctor Leave"
)
def delete_doctor_leave_endpoint(
    doctor_id: int,
    leave_id: int,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Cancel or remove a previously scheduled leave.
    """
    return delete_doctor_leave(doctor_id, leave_id, db)
