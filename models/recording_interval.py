from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Time
from sqlalchemy.types import JSON
from .base import Base
from common.enums import IntervalCategory
import json
from api.v1.recording_intervals.schema import RecordingIntervalResponse


class RecordingInterval(Base):
    __tablename__ = "recording_interval"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recording.id"), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    description = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Will store enum values as strings
    issue = Column(String)
    short_title = Column(String, nullable=False)
    timestamp_descriptions = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    deleted_at = Column(DateTime, nullable=True)

    def set_category(self, category: IntervalCategory):
        """Set the category using the Enum"""
        self.category = category.value

    def get_category(self) -> IntervalCategory:
        """Get the category as an Enum"""
        return IntervalCategory(self.category)
