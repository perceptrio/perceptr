from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime, UTC
from .base import Base


class Org(Base):
    __tablename__ = "org"
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        String(50),
        nullable=False,
        default=lambda: f"proj_{''.join(__import__('random').choices(__import__('string').ascii_letters + __import__('string').digits, k=22))}",
    )
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False, unique=True)
    password = Column(String(250), nullable=False)
    joined_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)
