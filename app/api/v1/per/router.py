import re

from common.services.s3 import s3_service
from core.constants import APIPath
from database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from . import service
from .schema import BatchUrlResponse, GenericResponse, SnapshotBuffer

router = APIRouter(prefix=f"{APIPath.V1}/per", tags=["sdk-api"])


@router.get(  # type: ignore
    "/{project_id}/check",
    response_model=GenericResponse,
)
def check_project_id(
    project_id: str,
    db: Session = Depends(get_db),
) -> GenericResponse:
    """Check if the project id is valid"""
    org = service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")
    return GenericResponse(success=True)


# r == recording
RECORDING_PATH = "/{project_id}/r"


# TODO: Delete this endpoint
@router.post(  # type: ignore
    RECORDING_PATH + "/events",
    response_model=GenericResponse,
)
async def record_events(
    project_id: str,
    snapshot_buffer: SnapshotBuffer,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> GenericResponse:
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


@router.get(  # type: ignore
    RECORDING_PATH + "/{session_id}/batch",
    response_model=BatchUrlResponse,
)
async def get_batch_upload_url(
    project_id: str,
    session_id: str,
    db: Session = Depends(get_db),
) -> BatchUrlResponse:
    """Generate a presigned URL for batch upload with automatic batch numbering"""
    # Validate project ID and get org
    org = service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")

    try:
        # List existing batches for this session
        session_prefix = f"{org.id}/{session_id}/"
        existing_files = s3_service.list_folder_contents(session_prefix)

        # Find the highest batch number
        batch_pattern = re.compile(r"batch_(\d+)\.json$")
        max_batch = 0

        for file in existing_files:
            if match := batch_pattern.search(file["key"]):
                batch_num = int(match.group(1))
                max_batch = max(max_batch, batch_num)

        # Generate the next batch number and file path
        next_batch = max_batch + 1
        file_path = f"{session_prefix}batch_{next_batch}.json"

        # Generate presigned URL for upload
        upload_url = s3_service.get_upload_url(
            file_path=file_path,
            content_type="application/json",
            expiration=3600,  # 1 hour expiration
        )

        return BatchUrlResponse(
            success=True, url=upload_url, batch_number=next_batch, file_path=file_path
        )
    except Exception as e:
        # Log the error
        import traceback

        traceback.print_exc()
        # Return a friendly error
        return BatchUrlResponse(
            success=False, message=f"Failed to generate batch upload URL: {str(e)}"
        )
