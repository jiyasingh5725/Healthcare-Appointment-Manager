from datetime import datetime, timezone
from sqlalchemy import Column, Integer, SmallInteger, String, Date, Time, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class DoctorWorkingHours(Base):
    __tablename__ = "doctor_working_hours"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Monday, 1=Tuesday, ..., 6=Sunday
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)

    # Relationships
    doctor = relationship("Doctor", back_populates="working_hours")

    def __repr__(self):
        return f"<DoctorWorkingHours(id={self.id}, doctor_id={self.doctor_id}, day_of_week={self.day_of_week}, {self.start_time}-{self.end_time})>"


class DoctorLeave(Base):
    __tablename__ = "doctor_leaves"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True)
    leave_date = Column(Date, nullable=False, index=True)
    reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    doctor = relationship("Doctor", back_populates="leaves")

    def __repr__(self):
        return f"<DoctorLeave(id={self.id}, doctor_id={self.doctor_id}, leave_date={self.leave_date})>"
