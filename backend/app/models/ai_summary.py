from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship

from app.database import Base


class AISummary(Base):
    __tablename__ = "ai_summaries"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False, index=True)
    summary_type = Column(String(50), default="PREVISIT", nullable=False, index=True)
    urgency_level = Column(String(20), nullable=True)  # Low, Medium, High
    chief_complaint = Column(Text, nullable=True)
    suggested_questions = Column(Text, nullable=True)  # JSON-encoded array of questions
    summary_text = Column(Text, nullable=True)
    model_name = Column(String(100), default="gemini-1.5-flash", nullable=False)
    status = Column(String(50), default="SUCCESS", nullable=False)  # SUCCESS, FALLBACK, FAILED
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    appointment = relationship("Appointment", foreign_keys=[appointment_id], backref="ai_summaries")

    def __repr__(self) -> str:
        return f"<AISummary(id={self.id}, appointment_id={self.appointment_id}, urgency='{self.urgency_level}', status='{self.status}')>"
