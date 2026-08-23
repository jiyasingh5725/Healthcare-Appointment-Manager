from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User, UserRole
from app.models.doctor import Doctor
from app.schemas.doctor import (
    DoctorCreateRequest,
    DoctorUpdateRequest,
    DoctorStatusUpdateRequest,
    DoctorResponse,
)
from app.utils.security import hash_password
from app.utils.dependencies import require_admin
from app.routes.doctors import _serialize_doctor

router = APIRouter(prefix="/admin", tags=["Admin Doctor Management"])


@router.post(
    "/doctors",
    response_model=DoctorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: Create New Doctor"
)
def create_doctor(
    payload: DoctorCreateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Create a new doctor account with associated User(role=DOCTOR) and Doctor profile.
    Executed in an atomic database transaction.
    """
    normalized_email = payload.email.lower().strip()

    # 1. Validate email uniqueness
    existing_user = db.query(User).filter(User.email == normalized_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{normalized_email}' already exists."
        )

    # 2. Validate slot duration
    if payload.slot_duration < 10 or payload.slot_duration > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot duration must be between 10 and 120 minutes."
        )

    # 3. Validate specialization
    if not payload.specialization or not payload.specialization.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Specialization is required."
        )

    try:
        # Atomic Transaction: Create User + Doctor
        hashed_password = hash_password(payload.password)

        new_user = User(
            name=payload.name.strip(),
            email=normalized_email,
            password_hash=hashed_password,
            role=UserRole.DOCTOR,
            phone=payload.phone.strip() if payload.phone else None,
            is_active=payload.is_active,
        )
        db.add(new_user)
        db.flush()  # Flush to generate new_user.id

        new_doctor = Doctor(
            user_id=new_user.id,
            specialization=payload.specialization.strip(),
            qualification=payload.qualification.strip() if payload.qualification else None,
            experience=payload.experience,
            slot_duration=payload.slot_duration,
            is_active=payload.is_active,
        )
        db.add(new_doctor)
        db.commit()
        db.refresh(new_doctor)
        db.refresh(new_user)

        return _serialize_doctor(new_doctor)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create doctor: {str(e)}"
        )


@router.put(
    "/doctors/{doctor_id}",
    response_model=DoctorResponse,
    summary="Admin: Update Doctor Details"
)
def update_doctor(
    doctor_id: int,
    payload: DoctorUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Update doctor professional profile and associated user details.
    """
    doc = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID #{doctor_id} not found."
        )

    # Validate slot duration
    if payload.slot_duration < 10 or payload.slot_duration > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot duration must be between 10 and 120 minutes."
        )

    try:
        # Update user attributes
        if doc.user:
            doc.user.name = payload.name.strip()
            doc.user.phone = payload.phone.strip() if payload.phone else None
            doc.user.is_active = payload.is_active

        # Update doctor attributes
        doc.specialization = payload.specialization.strip()
        doc.qualification = payload.qualification.strip() if payload.qualification else None
        doc.experience = payload.experience
        doc.slot_duration = payload.slot_duration
        doc.is_active = payload.is_active

        db.commit()
        db.refresh(doc)

        return _serialize_doctor(doc)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update doctor: {str(e)}"
        )


@router.patch(
    "/doctors/{doctor_id}/status",
    response_model=DoctorResponse,
    summary="Admin: Activate / Deactivate Doctor"
)
def update_doctor_status(
    doctor_id: int,
    payload: DoctorStatusUpdateRequest,
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Activate or deactivate a doctor and their login account.
    """
    doc = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID #{doctor_id} not found."
        )

    try:
        doc.is_active = payload.is_active
        if doc.user:
            doc.user.is_active = payload.is_active

        db.commit()
        db.refresh(doc)

        return _serialize_doctor(doc)

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update doctor status: {str(e)}"
        )


@router.get(
    "/metrics",
    summary="Admin: Get System-wide Operational & Clinical Metrics"
)
def get_admin_metrics(
    admin_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Retrieve real-time aggregated metrics across users, doctors, appointments,
    leave conflicts, and notification health.
    """
    from app.models.appointment import Appointment, AppointmentStatus
    from app.models.doctor_schedule import DoctorLeave
    from app.models.notification import Notification, NotificationStatus

    total_users = db.query(User).count()
    total_patients = db.query(User).filter(User.role == UserRole.PATIENT).count()
    total_staff = db.query(User).filter(User.role.in_([UserRole.DOCTOR, UserRole.ADMIN])).count()
    total_doctors = db.query(Doctor).count()
    active_doctors = db.query(Doctor).filter(Doctor.is_active == True).count()
    inactive_doctors = total_doctors - active_doctors
    
    total_appointments = db.query(Appointment).count()
    confirmed_appointments = db.query(Appointment).filter(Appointment.status == AppointmentStatus.CONFIRMED).count()
    completed_appointments = db.query(Appointment).filter(Appointment.status == AppointmentStatus.COMPLETED).count()
    cancelled_appointments = db.query(Appointment).filter(Appointment.status == AppointmentStatus.CANCELLED).count()
    rescheduled_appointments = db.query(Appointment).filter(Appointment.status == AppointmentStatus.RESCHEDULED).count()

    total_leaves = db.query(DoctorLeave).count()
    leave_conflicts_resolved = db.query(Appointment).filter(
        Appointment.cancellation_reason.ilike("%leave%")
    ).count()

    notif_sent = db.query(Notification).filter(Notification.status == NotificationStatus.SENT.value).count()
    notif_failed = db.query(Notification).filter(Notification.status == NotificationStatus.FAILED.value).count()
    notif_pending = db.query(Notification).filter(Notification.status.in_([NotificationStatus.PENDING.value, NotificationStatus.RETRYING.value])).count()
    total_notifs = db.query(Notification).count()
    notif_success_rate = round((notif_sent / total_notifs * 100), 1) if total_notifs > 0 else 100.0

    return {
        "success": True,
        "users": {
            "total": total_users,
            "patients": total_patients,
            "staff": total_staff,
            "doctors": total_doctors,
            "active_doctors": active_doctors,
            "inactive_doctors": inactive_doctors
        },
        "appointments": {
            "total": total_appointments,
            "confirmed": confirmed_appointments,
            "completed": completed_appointments,
            "cancelled": cancelled_appointments,
            "rescheduled": rescheduled_appointments
        },
        "leaves": {
            "total_leaves": total_leaves,
            "leave_conflicts_resolved": leave_conflicts_resolved
        },
        "notifications": {
            "total": total_notifs,
            "sent": notif_sent,
            "failed": notif_failed,
            "pending": notif_pending,
            "success_rate": notif_success_rate
        }
    }

