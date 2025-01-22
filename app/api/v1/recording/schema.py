from datetime import datetime
from pydantic import BaseModel
from models.recording import Recording
from common.enums import RecordingType, VideoType


class RecordingUploadUrl(BaseModel):
    content_type: str
    recording_type: RecordingType = RecordingType.ORIGINAL
    expiration: int = 3600

class RecordingUploadUrlResponse(BaseModel):
    url: str

class RecordingDownloadUrl(BaseModel):
    recording_type: RecordingType = RecordingType.ORIGINAL
    expiration: int = 3600

class RecordingDownloadUrlResponse(BaseModel):
    url: str
 
class RecordingCreate(BaseModel):
    file_name: str
    file_size: int
    file_type: VideoType

class RecordingResponse(RecordingCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True