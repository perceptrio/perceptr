from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, Boolean
from datetime import datetime, UTC
from .base import Base
from common.enums import IntervalCategory


class Issue(Base):
    __tablename__ = "issue"
    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("org.id"), nullable=False)
    title = Column(String(250), nullable=False)
    description = Column(Text, nullable=True)
    recommendation = Column(Text, nullable=True)
    severity = Column(String(50), nullable=False)
    category = Column(String(50), nullable=False, default=IntervalCategory.NORMAL.value)
    is_resolved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)

    def set_category(self, category: IntervalCategory):
        """Set the category using the Enum"""
        self.category = category.value

    def get_category(self) -> IntervalCategory:
        """Get the category as an Enum"""
        return IntervalCategory(self.category)

