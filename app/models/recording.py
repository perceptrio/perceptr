from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, UTC
from .base import Base

class Recording(Base):
    __tablename__ = 'recording'
    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey('org.id'), nullable=False)
    file_name = Column(String(250), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    deleted_at = Column(DateTime, nullable=True)
