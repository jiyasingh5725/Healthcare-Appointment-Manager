from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from app.database import Base


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    notes = Column(Text, nullable=True)
    follow_up_instructions = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    appointment = relationship("Appointment", foreign_keys=[appointment_id], backref="prescription")
    doctor = relationship("Doctor", foreign_keys=[doctor_id], backref="doctor_prescriptions")
    patient = relationship("User", foreign_keys=[patient_id], backref="patient_prescriptions")
    medications = relationship("Medication", back_populates="prescription", cascade="all, delete-orphan", lazy="joined")

    def __repr__(self) -> str:
        return f"<Prescription(id={self.id}, appointment_id={self.appointment_id}, doctor_id={self.doctor_id})>"


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    medication_name = Column(String(255), nullable=False)
    dosage = Column(String(100), nullable=False)  # e.g. "500mg"
    frequency = Column(String(100), nullable=False)  # e.g. "Twice daily after meals"
    duration = Column(String(100), nullable=False)  # e.g. "7 days"
    instructions = Column(Text, nullable=True)  # e.g. "Take with a full glass of water"
    reminder_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    prescription = relationship("Prescription", back_populates="medications")

    def __repr__(self) -> str:
        return f"<Medication(id={self.id}, name='{self.medication_name}', dosage='{self.dosage}')>"
