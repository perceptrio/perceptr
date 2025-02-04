from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from datetime import datetime, UTC
from .base import Base
from common.enums import AnalysisStatus, VideoType


class PydanticRecording(BaseModel):
    id: int
    file_name: str
    file_size: int
    file_type: VideoType
    file_duration: float | None
    org_id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    analysis_status: AnalysisStatus
    analysis_error: str | None
    analysis_progress: int
    short_title: str | None
    summary: str | None
    tags: str | None


class Recording(Base):
    __tablename__ = "recording"
    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey("org.id"), nullable=False)
    file_name = Column(String(250), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)
    file_duration = Column(Float, nullable=True)  # Duration in seconds
    analysis_status = Column(
        String(50), nullable=False, default=AnalysisStatus.PENDING.value
    )
    analysis_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )
    deleted_at = Column(DateTime, nullable=True)
    analysis_progress = Column(Integer, nullable=False, default=0)
    short_title = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    tags = Column(String(250), nullable=True)

    def set_analysis_status(self, status: AnalysisStatus):
        self.analysis_status = status.value

    def get_analysis_status(self) -> AnalysisStatus:
        return AnalysisStatus(self.analysis_status)

    def convert_model_to_schema(self) -> PydanticRecording:
        return PydanticRecording(
            id=self.id,
            file_name=self.file_name,
            file_size=self.file_size,
            file_type=self.file_type,
            file_duration=self.file_duration,
            org_id=self.org_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            deleted_at=self.deleted_at,
            analysis_status=self.analysis_status,
            analysis_error=self.analysis_error,
            analysis_progress=self.analysis_progress,
            short_title=self.short_title,
            summary=self.summary,
            tags=self.tags,
        )
