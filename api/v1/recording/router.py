from datetime import datetime
from typing import List

from api.v1.recording import service
from common.middleware.auth_token import GetPayload
from common.services.s3 import s3_service
from common.types import TokenPayload
from core.constants import APIPath
from database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from .schema import (
    DeleteFileBody,
    RecordingCreateForUpload,
    RecordingDownloadUrl,
    RecordingDownloadUrlResponse,
    RecordingResponse,
    RecordingUploadUrl,
    RecordingUploadUrlResponse,
)

router = APIRouter(prefix=f"{APIPath.V1}/recordings", tags=["recordings"])


@router.post("/{recording_name}/upload", response_model=RecordingUploadUrlResponse)
def get_recording_upload_url(
    recording_name: str,
    recording_upload_url: RecordingUploadUrl,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    url, key = service.get_recording_upload_url(
        recording_name,
        payload.org.id,
        db,
        recording_upload_url,
    )
    return RecordingUploadUrlResponse(url=url, key=key)


@router.post("/download", response_model=RecordingDownloadUrlResponse)
def get_recording_download_url(
    recording_download_url: RecordingDownloadUrl,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    url = service.get_recording_download_url(payload.org.id, db, recording_download_url)
    type = service.get_recording_download_type(recording_download_url)
    return RecordingDownloadUrlResponse(url=url, type=type)


@router.post("/", response_model=RecordingResponse)
def create_recording(
    recording: RecordingCreateForUpload,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    recording = service.create_recording_for_upload(db, payload.org.id, recording)
    return recording


@router.get("/{recording_id}", response_model=RecordingResponse)
def get_recording(
    recording_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    recording = service.get_recording(db, recording_id, payload.org.id)
    return recording


@router.get("/", response_model=List[RecordingResponse])
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
    return recordings


@router.post("/file/delete", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    body: DeleteFileBody,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
):
    print(f"{payload.org.id}/{body.key}")
    s3_service.delete_file(f"{payload.org.id}/{body.key}")
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
        service.check_recording_belonging_to_org(db, recording_id, payload.org.id)
        background_tasks.add_task(
            service.analyze_recording, payload.org.id, recording_id
        )
        return {"message": f"Analysis started for recording {recording_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
