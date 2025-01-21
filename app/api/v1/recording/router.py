from fastapi import APIRouter, Depends

from core.constants import APIPath
from schemas.recording_schema import RecordingDownloadUrl, RecordingUploadUrl, RecordingUploadUrlResponse, RecordingDownloadUrlResponse
from api.v1.recording import service
from common.types import TokenPayload  
from typing_extensions import Annotated
from common.middleware import GetPayload
from sqlalchemy.orm import Session
from database import get_db
from typing import List
from schemas.recording_schema import RecordingResponse, RecordingCreate
from fastapi import status
router = APIRouter(prefix=f"{APIPath.V1}/recordings", tags=["recordings"])

@router.post("/{file_name}/upload", response_model=RecordingUploadUrlResponse)
def get_recording_upload_url(file_name: str, recording_upload_url: RecordingUploadUrl,payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))], db: Session = Depends(get_db)):
    url = service.get_recording_upload_url(file_name, payload.org.id, db, recording_upload_url,)
    return RecordingUploadUrlResponse(url=url)

@router.post("/{file_name}/download", response_model=RecordingDownloadUrlResponse)
def get_recording_download_url(file_name: str, recording_download_url: RecordingDownloadUrl, payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))], db: Session = Depends(get_db)):
    url = service.get_recording_download_url(file_name, payload.org.id, db, recording_download_url)
    return RecordingDownloadUrlResponse(url=url)

@router.post('/', response_model=RecordingResponse)
def create_recording(recording: RecordingCreate, payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))], db: Session = Depends(get_db)):
    recording = service.create_recording(db,payload.org.id, recording)
    return RecordingResponse(recording=recording)

@router.get('/{recording_id}', response_model=RecordingResponse)
def get_recording(recording_id: int, payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))], db: Session = Depends(get_db)):
    recording = service.get_recording(db, recording_id, payload.org.id)
    return RecordingResponse(recording=recording)

@router.get('/', response_model=List[RecordingResponse])
def get_recordings_for_org(payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    recordings = service.get_recordings(db, payload.org.id, skip, limit)
    return recordings

@router.delete('/{recording_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(recording_id: int, payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))], db: Session = Depends(get_db)):
    service.soft_delete_recording(db, recording_id, payload.org.id)
    return