from datetime import date, time, datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator


DAYS_OF_WEEK_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
]


class WorkingHoursItem(BaseModel):
    """Configuration for a single day's working hours."""
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 1=Tuesday, ..., 6=Sunday")
    start_time: Optional[time] = Field(None, description="Starting time (HH:MM:SS)")
    end_time: Optional[time] = Field(None, description="Ending time (HH:MM:SS)")
    is_working: bool = Field(True, description="Whether doctor is available on this day")

    @model_validator(mode="after")
    def validate_time_range(self) -> "WorkingHoursItem":
        if self.is_working:
            if self.start_time is None or self.end_time is None:
                raise ValueError("start_time and end_time are required when is_working is true")
            if self.start_time >= self.end_time:
                raise ValueError("start_time must be earlier than end_time")
        return self


class WorkingHoursBulkUpdateRequest(BaseModel):
    """Payload to bulk-configure working hours for Monday through Sunday."""
    working_hours: list[WorkingHoursItem] = Field(..., description="List of working hour definitions for days of the week")


class WorkingHoursResponse(BaseModel):
    """Response schema for a day's working hours."""
    id: Optional[int] = None
    doctor_id: int
    day_of_week: int
    day_name: str
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_working: bool

    model_config = ConfigDict(from_attributes=True)


class DoctorLeaveCreateRequest(BaseModel):
    """Payload to schedule a doctor leave."""
    leave_date: date = Field(..., description="Target leave date (YYYY-MM-DD)")
    reason: Optional[str] = Field(None, max_length=255, description="Optional explanation for leave")


class DoctorLeaveResponse(BaseModel):
    """Response schema for a scheduled doctor leave."""
    id: int
    doctor_id: int
    leave_date: date
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoctorLeaveWithConflictsResponse(BaseModel):
    """Response returned upon leave creation including automatic cancellation & notification details."""
    leave: DoctorLeaveResponse
    affected_appointments_count: int = 0
    affected_appointments: list[dict[str, Any]] = []
    patients_to_notify: list[dict[str, Any]] = []
    notifications_prepared: int = 0
    calendar_sync_jobs_prepared: int = 0
    # Backward compatibility alias
    conflicting_appointments_count: int = 0
    conflicts: list[dict[str, Any]] = []
    message: str = "Leave scheduled successfully"

