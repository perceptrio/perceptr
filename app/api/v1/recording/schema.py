from datetime import datetime
from pydantic import BaseModel, field_validator
from common.enums import RecordingType, VideoType, AnalysisStatus


class RecordingUploadUrl(BaseModel):
    content_type: str
    recording_type: RecordingType = RecordingType.ORIGINAL
    expiration: int = 3600


class RecordingUploadUrlResponse(BaseModel):
    url: str
    key: str


class RecordingDownloadUrl(BaseModel):
    key: str
    expiration: int = 3600


class RecordingDownloadUrlResponse(BaseModel):
    url: str


class RecordingCreate(BaseModel):
    file_name: str  # key of file in s3
    file_size: int
    file_type: VideoType


class RecordingAnalysis(BaseModel):
    user_id: int
    recording_id: int
    recording_path: str


class DeleteFileBody(BaseModel):
    key: str


class RecordingResponse(RecordingCreate):
    id: int
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
    tags: list[str] | None

    class Config:
        from_attributes = True

    @field_validator("tags", mode="before")
    @classmethod
    def split_tags(cls, value: str | None) -> list[str] | None:
        if value is None:
            return None
        return [tag.strip() for tag in value.split(",") if tag.strip()]
