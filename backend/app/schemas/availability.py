from datetime import date, time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class SlotStatusEnum(str, Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"
    BOOKED = "BOOKED"


class TimeSlot(BaseModel):
    """Dynamically calculated time slot."""
    start_time: time = Field(..., description="Slot start time (HH:MM:SS)")
    end_time: time = Field(..., description="Slot end time (HH:MM:SS)")
    status: SlotStatusEnum = Field(SlotStatusEnum.AVAILABLE, description="Availability status")
    is_available: bool = Field(True, description="True if available for booking")

    model_config = ConfigDict(from_attributes=True)


class DoctorAvailabilityResponse(BaseModel):
    """Calculated dynamic doctor availability for a specific calendar date."""
    doctor_id: int
    doctor_name: str
    specialization: str
    date: date
    day_name: str
    slot_duration: int
    is_working_day: bool
    is_on_leave: bool
    leave_reason: Optional[str] = None
    total_slots: int
    available_slots_count: int
    slots: list[TimeSlot]
    message: str

    model_config = ConfigDict(from_attributes=True)
