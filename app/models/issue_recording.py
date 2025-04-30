from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer

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
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)
