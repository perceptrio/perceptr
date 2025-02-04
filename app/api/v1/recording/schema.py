from pydantic import BaseModel
from common.enums import RecordingType, VideoType


class RecordingUploadUrl(BaseModel):
    content_type: str
    recording_type: RecordingType = RecordingType.ORIGINAL
    expiration: int = 3600


class RecordingUploadUrlResponse(BaseModel):
    url: str
    key: str


class RecordingDownloadUrl(BaseModel):
    recording_type: RecordingType = RecordingType.ORIGINAL
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
