from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class DoctorCreateRequest(BaseModel):
    """Schema for admin creating a doctor."""
    name: str = Field(..., min_length=2, max_length=120, description="Doctor's full name")
    email: EmailStr = Field(..., description="Doctor's login email address")
    password: str = Field(..., min_length=6, max_length=128, description="Initial password")
    phone: Optional[str] = Field(None, max_length=30, description="Contact phone number")
    specialization: str = Field(..., min_length=2, max_length=120, description="Medical specialization (e.g. Cardiology)")
    qualification: Optional[str] = Field(None, max_length=150, description="Degrees & credentials (e.g. MBBS, MD)")
    experience: Optional[int] = Field(None, ge=0, le=70, description="Years of professional experience")
    slot_duration: int = Field(30, ge=10, le=120, description="Default appointment duration in minutes (10-120)")
    is_active: bool = Field(True, description="Account active status")


class DoctorUpdateRequest(BaseModel):
    """Schema for admin updating an existing doctor."""
    name: str = Field(..., min_length=2, max_length=120, description="Doctor's full name")
    phone: Optional[str] = Field(None, max_length=30, description="Contact phone number")
    specialization: str = Field(..., min_length=2, max_length=120, description="Medical specialization")
    qualification: Optional[str] = Field(None, max_length=150, description="Degrees & credentials")
    experience: Optional[int] = Field(None, ge=0, le=70, description="Years of professional experience")
    slot_duration: int = Field(30, ge=10, le=120, description="Appointment slot duration in minutes")
    is_active: bool = Field(True, description="Active status")


class DoctorStatusUpdateRequest(BaseModel):
    """Schema for toggling doctor active status."""
    is_active: bool = Field(..., description="Set active (true) or inactive (false)")


class DoctorResponse(BaseModel):
    """Response schema for doctor profile details."""
    id: int
    user_id: int
    name: str
    email: str
    phone: Optional[str] = None
    specialization: str
    qualification: Optional[str] = None
    experience: Optional[int] = None
    slot_duration: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoctorListResponse(BaseModel):
    """Response schema for listing doctors."""
    total: int
    doctors: list[DoctorResponse]


class DoctorProfileUpdateRequest(BaseModel):
    """Schema for doctor updating their own profile and credentials."""
    name: Optional[str] = Field(None, min_length=2, max_length=120, description="Doctor's full name")
    phone: Optional[str] = Field(None, max_length=30, description="Contact phone number")
    specialization: Optional[str] = Field(None, min_length=2, max_length=120, description="Medical specialization")
    qualification: Optional[str] = Field(None, max_length=150, description="Degrees & credentials")
    experience: Optional[int] = Field(None, ge=0, le=70, description="Years of professional experience")
    slot_duration: Optional[int] = Field(None, ge=10, le=120, description="Appointment slot duration in minutes")


class DoctorAppointmentStatusUpdateRequest(BaseModel):
    """Schema for doctor updating an appointment status."""
    status: str = Field(..., description="Target status: COMPLETED, CANCELLED, etc.")
    cancellation_reason: Optional[str] = Field(None, max_length=500, description="Reason if cancelling")

