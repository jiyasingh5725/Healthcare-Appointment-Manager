from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.database import get_db
from app.models.doctor import Doctor
from app.models.user import User
from app.schemas.doctor import DoctorResponse, DoctorListResponse
from app.schemas.availability import DoctorAvailabilityResponse
from app.services.availability_service import calculate_doctor_availability

router = APIRouter(prefix="/doctors", tags=["Doctors"])


def _serialize_doctor(doc: Doctor) -> DoctorResponse:
    """Helper to convert Doctor ORM entity to DoctorResponse schema."""
    return DoctorResponse(
        id=doc.id,
        user_id=doc.user_id,
        name=doc.user.name if doc.user else "Unknown",
        email=doc.user.email if doc.user else "",
        phone=doc.user.phone if doc.user else None,
        specialization=doc.specialization,
        qualification=doc.qualification,
        experience=doc.experience,
        slot_duration=doc.slot_duration,
        is_active=bool(doc.is_active and (doc.user.is_active if doc.user else False)),
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "",
    response_model=list[DoctorResponse],
    summary="List Doctors"
)
def list_doctors(
    specialization: Optional[str] = Query(None, description="Filter by specialization"),
    search: Optional[str] = Query(None, description="Search by doctor name or qualification"),
    active_only: bool = Query(True, description="Filter for active doctors only"),
    db: Session = Depends(get_db)
):
    """
    Retrieve all doctors with optional filtering by specialization, keyword, and active status.
    """
    query = db.query(Doctor).join(Doctor.user).options(joinedload(Doctor.user))

    if active_only:
        query = query.filter(Doctor.is_active == True, User.is_active == True)

    if specialization and specialization.strip():
        query = query.filter(Doctor.specialization.ilike(f"%{specialization.strip()}%"))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.name.ilike(term),
                Doctor.qualification.ilike(term),
                Doctor.specialization.ilike(term)
            )
        )

    doctors = query.order_by(Doctor.id.asc()).all()
    return [_serialize_doctor(doc) for doc in doctors]


@router.get(
    "/{doctor_id}",
    response_model=DoctorResponse,
    summary="Get Doctor Details"
)
def get_doctor_by_id(doctor_id: int, db: Session = Depends(get_db)):
    """
    Retrieve details for a specific doctor by ID.
    """
    doc = db.query(Doctor).options(joinedload(Doctor.user)).filter(Doctor.id == doctor_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID #{doctor_id} not found."
        )

    return _serialize_doctor(doc)


@router.get(
    "/{doctor_id}/availability",
    response_model=DoctorAvailabilityResponse,
    summary="Get Doctor Dynamic Availability"
)
def get_doctor_availability_endpoint(
    doctor_id: int,
    target_date: date = Query(..., alias="date", description="Target calendar date (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Dynamically calculate consultation time slots for a doctor on a specific date.
    Calculates availability based on working hours, slot duration, scheduled leaves, and active bookings.
    """
    return calculate_doctor_availability(doctor_id, target_date, db)
