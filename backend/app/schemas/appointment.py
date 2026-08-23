from datetime import date, time, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.models.appointment import AppointmentStatus


class AppointmentCreateRequest(BaseModel):
    """Payload to book an appointment."""
    doctor_id: int = Field(..., description="ID of the doctor to book with")
    appointment_date: date = Field(..., description="Date of consultation (YYYY-MM-DD)")
    start_time: time = Field(..., description="Start time of consultation (HH:MM:SS)")
    end_time: Optional[time] = Field(None, description="Optional end time (computed from slot duration if omitted)")
    symptoms: Optional[str] = Field(None, max_length=1000, description="Optional patient symptoms / reason for consultation")


class AppointmentResponse(BaseModel):
    """Detailed response schema for an appointment."""
    id: int
    patient_id: int
    patient_name: str
    patient_email: str
    patient_phone: Optional[str] = None
    doctor_id: int
    doctor_name: str
    specialization: str
    appointment_date: date
    start_time: time
    end_time: time
    status: AppointmentStatus
    symptoms: Optional[str] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentListResponse(BaseModel):
    """List response schema for appointments."""
    appointments: list[AppointmentResponse]
    total_count: int


class AppointmentCancelRequest(BaseModel):
    """Payload to cancel an appointment."""
    reason: Optional[str] = Field("Cancelled by user", description="Reason for cancellation")


class AppointmentRescheduleRequest(BaseModel):
    """Payload to reschedule an appointment."""
    new_date: date = Field(..., description="New consultation date (YYYY-MM-DD)")
    new_start_time: time = Field(..., description="New start time (HH:MM:SS)")
    new_end_time: Optional[time] = Field(None, description="Optional new end time")

