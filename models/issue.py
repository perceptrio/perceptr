from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Text,
    Boolean,
)
from datetime import datetime, UTC
from .base import Base
from common.enums import IntervalCategory


class Issue(Base):
    __tablename__ = "issue"
    id = Column[int](Integer, primary_key=True, autoincrement=True)
    org_id = Column[int](Integer, ForeignKey("org.id"), nullable=False)
    title = Column[str](String(250), nullable=False)
    description = Column[str](Text, nullable=True)
    root_cause = Column[str](Text, nullable=True)
    recommendation = Column[str](Text, nullable=True)
    severity = Column[str](String(50), nullable=False)
    category = Column[str](
        String(50), nullable=False, default=IntervalCategory.NORMAL.value
    )
    type = Column[str](String(50), nullable=True)
    target = Column[str](String(500), nullable=True)
    confidence = Column[str](String(20), nullable=True)
    is_resolved = Column[bool](Boolean, nullable=False, default=False)
    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column[datetime](DateTime, nullable=True)

    def set_category(self, category: IntervalCategory):
        """Set the category using the Enum"""
        self.category = category.value

    def get_category(self) -> IntervalCategory:
        """Get the category as an Enum"""
        return IntervalCategory(self.category)
