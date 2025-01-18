from fastapi import APIRouter, Depends

from core.constants import APIPath
from schemas.recording_schema import RecordingDownloadUrl, RecordingUploadUrl, RecordingUploadUrlResponse, RecordingDownloadUrlResponse
from api.v1.recording import service
from common.types import TokenPayload  
from typing_extensions import Annotated
from common.middleware import GetPayload
router = APIRouter(prefix=f"{APIPath.V1}/recordings", tags=["recordings"])

@router.post("/{recording_id}/upload", response_model=RecordingUploadUrlResponse)
def get_recording_upload_url(recording_id: str, recording_upload_url: RecordingUploadUrl, payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))]):
    url = service.get_recording_upload_url(recording_id, recording_upload_url, payload.org.id)
    return RecordingUploadUrlResponse(url=url)

@router.post("/{recording_id}/download", response_model=RecordingDownloadUrlResponse)
def get_recording_download_url(recording_id: str, recording_download_url: RecordingDownloadUrl, payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))]):
    url = service.get_recording_download_url(recording_id, recording_download_url, payload.org.id)
    return RecordingDownloadUrlResponse(url=url)
