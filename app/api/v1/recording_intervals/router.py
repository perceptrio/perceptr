from fastapi import APIRouter, Depends
from core.constants import APIPath
from common.types import TokenPayload
from typing_extensions import Annotated
from common.middleware import GetPayload
from sqlalchemy.orm import Session
from database import get_db
from typing import List
from api.v1.recording_intervals import service
from api.v1.recording import service as recording_service
from api.v1.recording_intervals.schema import RecordingIntervalResponse

router = APIRouter(
    prefix=f"{APIPath.V1}/recording-intervals", tags=["recording-intervals"]
)


@router.get("/{recording_id}", response_model=List[RecordingIntervalResponse])
def get_recording_intervals_for_recording(
    recording_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    recording_service.check_recording_belonging_to_org(db, recording_id, payload.org.id)
    recording_intervals = service.get_recording_intervals_by_recording_id(
        db, recording_id
    )
    return recording_intervals
