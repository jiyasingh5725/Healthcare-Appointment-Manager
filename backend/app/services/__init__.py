"""Business logic services package."""

from app.services.doctor_schedule_service import (
    get_doctor_working_hours,
    update_doctor_working_hours,
    get_doctor_leaves,
    create_doctor_leave,
    delete_doctor_leave,
)
from app.services.availability_service import (
    calculate_doctor_availability,
)
from app.services.appointment_service import (
    book_appointment,
    get_user_appointments,
    get_appointment_by_id,
    clean_expired_holds,
)
from app.services.leave_conflict_service import (
    process_leave_conflicts,
)
from app.services.ai_summary_service import (
    generate_previsit_summary,
    get_previsit_summary,
    generate_postvisit_summary,
    get_postvisit_summary,
)
from app.services.prescription_service import (
    submit_consultation,
    create_prescription,
    get_appointment_prescription,
)

__all__ = [
    "get_doctor_working_hours",
    "update_doctor_working_hours",
    "get_doctor_leaves",
    "create_doctor_leave",
    "delete_doctor_leave",
    "calculate_doctor_availability",
    "book_appointment",
    "get_user_appointments",
    "get_appointment_by_id",
    "clean_expired_holds",
    "process_leave_conflicts",
    "generate_previsit_summary",
    "get_previsit_summary",
    "generate_postvisit_summary",
    "get_postvisit_summary",
    "submit_consultation",
    "create_prescription",
    "get_appointment_prescription",
]




