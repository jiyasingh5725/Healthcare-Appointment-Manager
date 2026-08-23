"""Pydantic schemas package."""

from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    TokenResponse,
    UserProfileUpdateRequest,
)
from app.schemas.doctor import (
    DoctorCreateRequest,
    DoctorUpdateRequest,
    DoctorStatusUpdateRequest,
    DoctorResponse,
    DoctorListResponse,
    DoctorProfileUpdateRequest,
    DoctorAppointmentStatusUpdateRequest,
)
from app.schemas.doctor_schedule import (
    WorkingHoursItem,
    WorkingHoursBulkUpdateRequest,
    WorkingHoursResponse,
    DoctorLeaveCreateRequest,
    DoctorLeaveResponse,
    DoctorLeaveWithConflictsResponse,
    DAYS_OF_WEEK_NAMES,
)
from app.schemas.availability import (
    SlotStatusEnum,
    TimeSlot,
    DoctorAvailabilityResponse,
)
from app.schemas.appointment import (
    AppointmentCreateRequest,
    AppointmentResponse,
    AppointmentListResponse,
)
from app.schemas.ai_summary import (
    PrevisitSummaryRequest,
    PrevisitSummaryResponse,
    MedicationScheduleItem,
    PostvisitSummaryRequest,
    PostvisitSummaryResponse,
)
from app.schemas.prescription import (
    MedicationItem,
    ConsultationSubmitRequest,
    PrescriptionCreateRequest,
    MedicationResponse,
    PrescriptionResponse,
)

__all__ = [
    "UserRegisterRequest",
    "UserLoginRequest",
    "UserResponse",
    "TokenResponse",
    "DoctorCreateRequest",
    "DoctorUpdateRequest",
    "DoctorStatusUpdateRequest",
    "DoctorResponse",
    "DoctorListResponse",
    "WorkingHoursItem",
    "WorkingHoursBulkUpdateRequest",
    "WorkingHoursResponse",
    "DoctorLeaveCreateRequest",
    "DoctorLeaveResponse",
    "DoctorLeaveWithConflictsResponse",
    "DAYS_OF_WEEK_NAMES",
    "SlotStatusEnum",
    "TimeSlot",
    "DoctorAvailabilityResponse",
    "AppointmentCreateRequest",
    "AppointmentResponse",
    "AppointmentListResponse",
    "PrevisitSummaryRequest",
    "PrevisitSummaryResponse",
    "MedicationScheduleItem",
    "PostvisitSummaryRequest",
    "PostvisitSummaryResponse",
    "MedicationItem",
    "ConsultationSubmitRequest",
    "PrescriptionCreateRequest",
    "MedicationResponse",
    "PrescriptionResponse",
]



