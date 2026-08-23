from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class MedicationItem(BaseModel):
    """Payload schema for an individual medication prescribed."""
    medication_name: str = Field(..., min_length=1, max_length=255, description="Name of the pharmaceutical/medication")
    dosage: str = Field(..., min_length=1, max_length=100, description="Dosage (e.g., 500mg, 10ml)")
    frequency: str = Field(..., min_length=1, max_length=100, description="Frequency (e.g., Twice daily after meals)")
    duration: str = Field(..., min_length=1, max_length=100, description="Duration (e.g., 7 days, 1 month)")
    instructions: Optional[str] = Field(None, description="Specific patient intake instructions or precautions")
    reminder_enabled: bool = Field(True, description="Whether to schedule patient medication reminders")


class ConsultationSubmitRequest(BaseModel):
    """Payload to submit physician clinical notes and complete consultation."""
    notes: Optional[str] = Field(None, description="Doctor clinical observations and diagnosis notes")
    follow_up_instructions: Optional[str] = Field(None, description="Follow-up advice and scheduled review timeline")


class PrescriptionCreateRequest(BaseModel):
    """Payload to submit clinical prescription with medications and complete consultation."""
    notes: Optional[str] = Field(None, description="Doctor clinical observations and diagnosis notes")
    follow_up_instructions: Optional[str] = Field(None, description="Follow-up advice and scheduled review timeline")
    medications: list[MedicationItem] = Field(default_factory=list, description="List of prescribed medications")


class MedicationResponse(BaseModel):
    """Response schema for a single prescribed medication."""
    id: int
    prescription_id: int
    medication_name: str
    dosage: str
    frequency: str
    duration: str
    instructions: Optional[str] = None
    reminder_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PrescriptionResponse(BaseModel):
    """Response schema for clinical prescription and medication breakdown."""
    id: int
    appointment_id: int
    doctor_id: int
    doctor_name: str
    doctor_specialization: str
    patient_id: int
    patient_name: str
    patient_email: str
    notes: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    medications: list[MedicationResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
