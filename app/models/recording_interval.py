from datetime import UTC, datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from .base import Base
from common.enums import IntervalCategory


class RecordingInterval(Base):
    __tablename__ = "recording_interval"

    id = Column(Integer, primary_key=True, index=True)
    recording_id = Column(Integer, ForeignKey("recording.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    summary = Column(String, nullable=False)
    category = Column(String, nullable=False)  # Will store enum values as strings
    issue = Column(String)
    
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    deleted_at = Column(DateTime, nullable=True)

    def set_category(self, category: IntervalCategory):
        """Set the category using the Enum"""
        self.category = category.value

    def get_category(self) -> IntervalCategory:
        """Get the category as an Enum"""
        return IntervalCategory(self.category)