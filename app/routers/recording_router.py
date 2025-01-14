from services import recording_service
from fastapi import APIRouter, Depends, HTTPException, status
from core.constants import APIPath
from schemas.recording_schema import RecordingAnalysis

router = APIRouter(prefix=f"{APIPath.V1}/recordings", tags=["recordings"])

@router.post("/analyze")
def analyze_recording(request: RecordingAnalysis):
    try:
        return recording_service.analyze_recording(request.user_id, request.recording_id, request.recording_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

