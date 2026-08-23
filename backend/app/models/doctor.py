from datetime import datetime, timezone
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.doctor_schedule import DoctorWorkingHours, DoctorLeave


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    specialization: Mapped[str] = mapped_column(String(120), nullable=False)
    qualification: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    experience: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Experience in years
    slot_duration: Mapped[int] = mapped_column(Integer, default=30, nullable=False)  # Duration in minutes
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="doctor")
    working_hours: Mapped[List["DoctorWorkingHours"]] = relationship("DoctorWorkingHours", back_populates="doctor", cascade="all, delete-orphan")
    leaves: Mapped[List["DoctorLeave"]] = relationship("DoctorLeave", back_populates="doctor", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Doctor(id={self.id}, user_id={self.user_id}, specialization='{self.specialization}')>"

