from pydantic import BaseModel
from common.enums import RecordingType

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
