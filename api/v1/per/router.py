import json
import os
import re
from typing import Any, Dict

from api.v1.org import service as org_service
from api.v1.recording import service as recording_service
from common.enums import AnalysisStatus
from common.services.logger import logger
from common.services.s3 import s3_service
from core.constants import APIPath
from database import get_db
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from utils.rrweb import merge_rrweb_batches

from . import service
from .schema import BatchUrlResponse, GenericResponse

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
    org = org_service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")
    return GenericResponse(success=True)


# r == recording
RECORDING_PATH = "/{project_id}/r"


@router.post(  # type: ignore
    RECORDING_PATH + "/{session_id}/process",
    response_model=GenericResponse,
)
async def process_session_api(
    project_id: str,
    session_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: Session = Depends(get_db),
) -> GenericResponse:
    """Trigger a session"""
    # Validate project ID
    org = org_service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")
    try:
        service.process_session(db, org.id, session_id, background_tasks, force)
        return GenericResponse(success=True, message="Session triggered successfully")
    except Exception as e:
        logger.error(f"Failed to process session", exc_info=e)
        raise HTTPException(status_code=400, detail=f"Failed to process session")


@router.get(  # type: ignore
    RECORDING_PATH + "/{session_id}/batch",
    response_model=BatchUrlResponse,
)
async def get_batch_upload_url(
    project_id: str,
    session_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> BatchUrlResponse:
    """Generate a presigned URL for batch upload with automatic batch numbering"""
    # Validate project ID and get org
    org = org_service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")

    # Upsert recording (create if not exist, else update updated_at)
    recording = service.upsert_session_for_batch(db, org.id, session_id)

    if recording is None:
        raise HTTPException(status_code=400, detail="Failed to get session")

    # If not in PENDING, keep logic as is
    if recording.analysis_status != AnalysisStatus.PENDING.value:
        raise HTTPException(status_code=400, detail="processing already started")
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

        # Schedule delayed check for stale recordings
        background_tasks.add_task(
            service.check_and_process_stale_recording,
            org.id,
            session_id,
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


@router.post(  # type: ignore
    RECORDING_PATH + "/{session_id}/batch-test",
    response_model=GenericResponse,
)
async def upload_test_batch(
    project_id: str,
    session_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
) -> GenericResponse:
    """
    Test route for the SDK.

    - Accepts a JSON body (`payload`).
    - Stores it locally under `tmp_session/{session_id}/batch_<n>.json`.
    - After each upload, merges all local batches into `tmp_session/{session_id}/events.json`.
    """
    # Validate project ID and get org (keeps behavior consistent with other routes)
    org = org_service.get_org_by_project_id(db, project_id)
    if org is None:
        raise HTTPException(status_code=400, detail="Invalid project id")

    try:
        # Local base directory for test sessions
        base_dir = os.path.join("tmp_session", session_id)
        os.makedirs(base_dir, exist_ok=True)

        # Discover existing batches to determine the next batch number
        batch_pattern = re.compile(r"batch_(\d+)\.json$")
        max_batch = 0

        for name in os.listdir(base_dir):
            if match := batch_pattern.search(name):
                batch_num = int(match.group(1))
                max_batch = max(max_batch, batch_num)

        batch_number = max_batch + 1

        # Save the incoming payload as the current batch_<n>.json locally
        batch_path = os.path.join(base_dir, f"batch_{batch_number}.json")
        with open(batch_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        # Collect all local batch files for this session
        batch_files: list[str] = []
        for name in os.listdir(base_dir):
            if batch_pattern.search(name):
                batch_files.append(os.path.join(base_dir, name))

        if not batch_files:
            return GenericResponse(
                success=False, message="No batch files found to merge"
            )

        # Use existing rrweb utility to merge all batches into events.json
        merged_path = merge_rrweb_batches(sorted(batch_files))
        logger.info(
            "Merged test batches into events.json",
            session_id=session_id,
            merged_path=merged_path,
        )

        return GenericResponse(
            success=True,
            message=f"Batch {batch_number} stored locally and events.json updated",
        )
    except HTTPException:
        # Re-raise HTTPExceptions unchanged
        raise
    except Exception as e:
        logger.error(
            "Failed to store test batch",
            exc_info=e,
            project_id=project_id,
            session_id=session_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to store batch for test session",
        )
