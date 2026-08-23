import enum
from sqlalchemy import Column, Integer, Date, Time, Enum, Text, ForeignKey, DateTime, Index, func
from sqlalchemy.orm import relationship

from app.database import Base


class AppointmentStatus(str, enum.Enum):
    HOLD = "HOLD"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RESCHEDULED = "RESCHEDULED"
    EXPIRED = "EXPIRED"


class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(
        Enum(AppointmentStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=AppointmentStatus.CONFIRMED,
        nullable=False,
        index=True
    )
    symptoms = Column(Text, nullable=True)
    hold_until = Column(DateTime(timezone=True), nullable=True, index=True)
    cancellation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    patient = relationship("User", foreign_keys=[patient_id], backref="patient_appointments")
    doctor = relationship("Doctor", foreign_keys=[doctor_id], backref="doctor_appointments")

    __table_args__ = (
        Index("ix_appointments_doctor_date_slot", "doctor_id", "appointment_date", "start_time"),
    )

    def __repr__(self) -> str:
        return f"<Appointment(id={self.id}, patient_id={self.patient_id}, doctor_id={self.doctor_id}, date={self.appointment_date}, time={self.start_time}, status='{self.status}')>"
