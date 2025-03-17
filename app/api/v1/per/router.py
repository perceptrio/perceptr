from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from core.constants import APIPath
from .schema import GenericResponse, SnapshotBuffer
from . import service
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter(prefix=f"{APIPath.V1}/per", tags=["sdk-api"])


@router.get(
    "/{project_id}/check",
)
def check_project_id(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Check if the project id is valid"""
    org = service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")
    return GenericResponse(success=True)


# r == recording
RECORDING_PATH = "/{project_id}/r"


@router.post(RECORDING_PATH + "/events", response_model=GenericResponse)
async def record_events(
    project_id: str,
    snapshot_buffer: SnapshotBuffer,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Record events from the SDK"""
    # Validate project ID
    org = service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")

    try:
        # Process the events
        service.process_events(db, org.id, snapshot_buffer, background_tasks)
        return GenericResponse(success=True, message="Events recorded successfully")
    except Exception as e:
        # Log the error
        import traceback

        traceback.print_exc()
        # Return a friendly error
        return GenericResponse(
            success=False, message=f"Failed to process events: {str(e)}"
        )
