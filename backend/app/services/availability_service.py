from datetime import date, time, datetime, timedelta, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text

from app.models.doctor import Doctor
from app.models.doctor_schedule import DoctorWorkingHours, DoctorLeave
from app.schemas.availability import (
    SlotStatusEnum,
    TimeSlot,
    DoctorAvailabilityResponse,
)
from app.schemas.doctor_schedule import DAYS_OF_WEEK_NAMES


def calculate_doctor_availability(
    doctor_id: int,
    target_date: date,
    db: Session
) -> DoctorAvailabilityResponse:
    """
    Dynamically calculate doctor consultation time slots for a given calendar date.
    Does NOT store generated slots as permanent database rows.
    """
    # 1. Fetch doctor with associated user record
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Doctor with ID #{doctor_id} not found."
        )

    if not doctor.is_active or (doctor.user and not doctor.user.is_active):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This physician's profile is currently inactive."
        )

    doctor_name = doctor.user.name if doctor.user else f"Doctor #{doctor.id}"
    specialization = doctor.specialization or "General Practice"
    day_idx = target_date.weekday()  # 0=Monday, 6=Sunday
    day_name = DAYS_OF_WEEK_NAMES[day_idx]

    # 2. Check Doctor Leaves for target_date
    leave = db.query(DoctorLeave).filter(
        DoctorLeave.doctor_id == doctor_id,
        DoctorLeave.leave_date == target_date
    ).first()

    if leave:
        return DoctorAvailabilityResponse(
            doctor_id=doctor.id,
            doctor_name=doctor_name,
            specialization=specialization,
            date=target_date,
            day_name=day_name,
            slot_duration=doctor.slot_duration,
            is_working_day=True,
            is_on_leave=True,
            leave_reason=leave.reason,
            total_slots=0,
            available_slots_count=0,
            slots=[],
            message=f"Dr. {doctor_name} is on leave on {target_date}{' (' + leave.reason + ')' if leave.reason else ''}."
        )

    # 3. Check Doctor Working Hours for day_of_week
    working_hours = db.query(DoctorWorkingHours).filter(
        DoctorWorkingHours.doctor_id == doctor_id,
        DoctorWorkingHours.day_of_week == day_idx
    ).first()

    if not working_hours:
        return DoctorAvailabilityResponse(
            doctor_id=doctor.id,
            doctor_name=doctor_name,
            specialization=specialization,
            date=target_date,
            day_name=day_name,
            slot_duration=doctor.slot_duration,
            is_working_day=False,
            is_on_leave=False,
            leave_reason=None,
            total_slots=0,
            available_slots_count=0,
            slots=[],
            message=f"Dr. {doctor_name} is not scheduled to work on {day_name}s."
        )

    # 4. Fetch Booked Appointments & Active Holds on target_date
    from app.models.appointment import Appointment, AppointmentStatus

    booked_times = set()
    held_times = set()
    now_utc = datetime.now(timezone.utc)

    existing_appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == target_date,
        Appointment.status.in_([AppointmentStatus.HOLD, AppointmentStatus.CONFIRMED])
    ).all()

    for app in existing_appointments:
        if app.status == AppointmentStatus.CONFIRMED:
            booked_times.add(app.start_time)
        elif app.status == AppointmentStatus.HOLD:
            if app.hold_until and app.hold_until.replace(tzinfo=timezone.utc if app.hold_until.tzinfo is None else app.hold_until.tzinfo) > now_utc:
                held_times.add(app.start_time)
            # Expired holds are not added to held_times, making slot AVAILABLE

    # 5. Dynamically Generate Slots
    slot_duration = doctor.slot_duration or 30
    duration_delta = timedelta(minutes=slot_duration)
    start_dt = datetime.combine(target_date, working_hours.start_time)
    end_dt = datetime.combine(target_date, working_hours.end_time)

    slots: list[TimeSlot] = []
    curr = start_dt

    while curr + duration_delta <= end_dt:
        s_time = curr.time()
        e_time = (curr + duration_delta).time()

        if s_time in booked_times:
            status_val = SlotStatusEnum.BOOKED
            is_avail = False
        elif s_time in held_times:
            status_val = SlotStatusEnum.HELD
            is_avail = False
        else:
            status_val = SlotStatusEnum.AVAILABLE
            is_avail = True

        slots.append(
            TimeSlot(
                start_time=s_time,
                end_time=e_time,
                status=status_val,
                is_available=is_avail
            )
        )
        curr += duration_delta

    available_count = sum(1 for s in slots if s.is_available)

    return DoctorAvailabilityResponse(
        doctor_id=doctor.id,
        doctor_name=doctor_name,
        specialization=specialization,
        date=target_date,
        day_name=day_name,
        slot_duration=slot_duration,
        is_working_day=True,
        is_on_leave=False,
        leave_reason=None,
        total_slots=len(slots),
        available_slots_count=available_count,
        slots=slots,
        message=f"{available_count} slot(s) available on {day_name}, {target_date}."
    )
