from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship, synonym

from app.database import Base


class NotificationType(str, Enum):
    BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
    APPOINTMENT_REMINDER = "APPOINTMENT_REMINDER"
    CANCELLATION = "CANCELLATION"
    RESCHEDULE = "RESCHEDULE"
    LEAVE_NOTIFICATION = "LEAVE_NOTIFICATION"
    MEDICATION_REMINDER = "MEDICATION_REMINDER"


class NotificationChannel(str, Enum):
    EMAIL = "EMAIL"
    IN_APP = "IN_APP"
    SMS = "SMS"


class NotificationStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Notification Details & Types (mapped to 'type' column for compatibility)
    type = Column("type", String(50), default=NotificationType.BOOKING_CONFIRMATION.value, nullable=False, index=True)
    channel = Column(String(20), default=NotificationChannel.EMAIL.value, nullable=False, index=True)
    status = Column("status", String(20), default=NotificationStatus.PENDING.value, nullable=False, index=True)
    email_job_status = Column("email_job_status", String(50), default="PENDING", nullable=False)
    
    # Delivery Diagnostics & Retry Tracking
    retry_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Message Content
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    
    # Additional background pipeline fields
    calendar_job_status = Column(String(50), default="PREPARED", nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Synonyms for seamless backwards compatibility
    notification_type = synonym("type")

    def __init__(self, **kwargs):
        if "status" in kwargs and "email_job_status" not in kwargs:
            kwargs["email_job_status"] = kwargs["status"]
        elif "email_job_status" in kwargs and "status" not in kwargs:
            kwargs["status"] = kwargs["email_job_status"]
        if "notification_type" in kwargs and "type" not in kwargs:
            kwargs["type"] = kwargs["notification_type"]
        super().__init__(**kwargs)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="user_notifications")
    appointment = relationship("Appointment", foreign_keys=[appointment_id], backref="appointment_notifications")

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type='{self.notification_type}', status='{self.status}', retries={self.retry_count})>"
