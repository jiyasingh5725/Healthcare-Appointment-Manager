from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.database import Base


class CalendarEvent(Base):
    """
    Google Calendar Event model tracking synchronization state for appointments.
    """
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    appointment_id: Mapped[int] = mapped_column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    google_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    calendar_id: Mapped[str] = mapped_column(String(255), default="primary", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="CONFIRMED", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    appointment = relationship("Appointment", foreign_keys=[appointment_id], backref="calendar_event")
    user = relationship("User", foreign_keys=[user_id], backref="calendar_events")

    def __repr__(self) -> str:
        return f"<CalendarEvent(id={self.id}, appointment_id={self.appointment_id}, google_event_id='{self.google_event_id}', status='{self.status}')>"


class UserGoogleOAuth(Base):
    """
    Secure server-side storage for Google Calendar OAuth 2.0 credentials.
    Tokens are NEVER exposed in frontend API responses.
    """
    __tablename__ = "user_google_oauth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scope: Mapped[str] = mapped_column(String(500), default="https://www.googleapis.com/auth/calendar.events", nullable=False)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    google_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship
    user = relationship("User", foreign_keys=[user_id], backref="google_oauth")

    def __repr__(self) -> str:
        return f"<UserGoogleOAuth(user_id={self.user_id}, is_connected={self.is_connected}, google_email='{self.google_email}')>"

