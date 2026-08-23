from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class PrevisitSummaryRequest(BaseModel):
    """Payload to trigger pre-visit AI symptom summarization."""
    symptoms: Optional[str] = Field(None, description="Optional symptoms override if updated before confirmation")


class PrevisitSummaryResponse(BaseModel):
    """Response schema for Pre-visit AI symptom summary."""
    id: int
    appointment_id: int
    summary_type: str = "PREVISIT"
    urgency_level: str = Field(..., description="Triage urgency: Low, Medium, High")
    chief_complaint: str
    suggested_questions: list[str] = Field(default_factory=list, description="Three suggested questions for physician")
    summary_text: Optional[str] = None
    model_name: str
    status: str  # SUCCESS, FALLBACK, FAILED
    error_message: Optional[str] = None
    disclaimer: str = "AI-generated decision-support triage only; not a clinical diagnosis."
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicationScheduleItem(BaseModel):
    """Patient-friendly medication schedule item."""
    medicine: str = Field(..., description="Name of medicine/drug")
    dosage: str = Field(..., description="Dosage quantity")
    frequency: str = Field(..., description="Schedule/intake frequency")
    duration: str = Field(..., description="Duration of treatment course")


class PostvisitSummaryRequest(BaseModel):
    """Payload to trigger post-visit AI summarization."""
    notes_override: Optional[str] = Field(None, description="Optional notes override for manual testing/refresh")


class PostvisitSummaryResponse(BaseModel):
    """Response schema for patient-friendly Post-visit AI summary."""
    id: int
    appointment_id: int
    summary_type: str = "POST_VISIT"
    summary: str = Field(..., description="Patient-friendly plain language visit summary")
    medication_schedule: list[MedicationScheduleItem] = Field(default_factory=list, description="Medication schedule")
    follow_up_steps: list[str] = Field(default_factory=list, description="Actionable follow-up steps")
    summary_text: Optional[str] = None
    model_name: str
    status: str  # SUCCESS, FALLBACK, FAILED
    error_message: Optional[str] = None
    disclaimer: str = "AI-generated patient summary; does not replace professional medical advice."
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

