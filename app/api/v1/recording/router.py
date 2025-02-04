from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from models.recording import PydanticRecording
from core.constants import APIPath
from .schema import (
    RecordingDownloadUrl,
    RecordingUploadUrl,
    RecordingUploadUrlResponse,
    RecordingDownloadUrlResponse,
)
from api.v1.recording import service
from common.types import TokenPayload
from typing_extensions import Annotated
from common.middleware import GetPayload
from sqlalchemy.orm import Session
from database import get_db
from typing import List
from .schema import RecordingCreate
from fastapi import status
from common.services.s3 import s3_service

router = APIRouter(prefix=f"{APIPath.V1}/recordings", tags=["recordings"])


@router.post("/{recording_name}/upload", response_model=RecordingUploadUrlResponse)
def get_recording_upload_url(
    recording_name: str,
    recording_upload_url: RecordingUploadUrl,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    url = service.get_recording_upload_url(
        recording_name,
        payload.org.id,
        db,
        recording_upload_url,
    )
    return RecordingUploadUrlResponse(url=url)


@router.post("/{key}/download", response_model=RecordingDownloadUrlResponse)
def get_recording_download_url(
    key: str,
    recording_download_url: RecordingDownloadUrl,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    url = service.get_recording_download_url(
        key, payload.org.id, db, recording_download_url
    )
    return RecordingDownloadUrlResponse(url=url)


@router.post("/", response_model=PydanticRecording)
def create_recording(
    recording: RecordingCreate,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    recording = service.create_recording(db, payload.org.id, recording)
    return recording.convert_model_to_schema()


@router.get("/{recording_id}", response_model=PydanticRecording)
def get_recording(
    recording_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    recording = service.get_recording(db, recording_id, payload.org.id)
    return recording.convert_model_to_schema()


@router.get("/", response_model=List[PydanticRecording])
def get_recordings_for_org(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
):
    recordings = service.get_recordings(
        db, payload.org.id, skip, limit, search, start_date, end_date
    )
    return [recording.convert_model_to_schema() for recording in recordings]


@router.delete("/file/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    key: str,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
):
    s3_service.delete_file(f"{payload.org.id}/recordings/{key}")
    return


@router.delete("/{recording_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(
    recording_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    service.soft_delete_recording(db, recording_id, payload.org.id)
    return


@router.delete("/{recording_id}/hard", status_code=status.HTTP_204_NO_CONTENT)
def delete_recording(
    recording_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    service.hard_delete_recording(db, recording_id, payload.org.id)
    return


@router.get("/{recording_id}/analyze")
def analyze_recording(
    recording_id: int,
    background_tasks: BackgroundTasks,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    try:
        recording = service.check_recording_belonging_to_org(
            db, recording_id, payload.org.id
        )
        background_tasks.add_task(
            service.analyze_recording, db, payload.org.id, recording_id, recording
        )
        return {"message": f"Analysis started for recording {recording_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
