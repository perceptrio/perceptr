from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from .base import Base


class IssueRecording(Base):
    __tablename__ = "issue_recording"
    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("org.id"), nullable=False)
    issue_id = Column(Integer, ForeignKey("issue.id"), nullable=False)
    recording_id = Column(Integer, ForeignKey("recording.id"), nullable=False)
    recording_interval_id = Column(
        Integer, ForeignKey("recording_interval.id"), nullable=False
    )
    type = Column(String(50), nullable=True)
    target = Column(String(500), nullable=True)
    confidence = Column(String(20), nullable=True)
    timestamp = Column(String(8), nullable=True)  # MM:SS format
    frequency = Column(Integer, nullable=True)
    severity = Column(String(20), nullable=True)
    category = Column(String(50), nullable=True)
    root_cause = Column(Text, nullable=True)
    reproduction_steps = Column(Text, nullable=True)
    analysis_tier = Column(String(20), nullable=True)  # tier0|tier1|tier2|video
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)
