from datetime import UTC, datetime, timedelta
from threading import Lock

from api.v1.per.schema import GenericResponse
from api.v1.uxaudit import service
from common.services.logger import logger
from common.services.s3 import s3_service
from core.constants import APIPath
from fastapi import APIRouter, BackgroundTasks, HTTPException

from .schema import (
    LeadUXAuditRequest,
    UploadRequest,
    UploadResponse,
    UXAuditRequest,
    UXAuditResponse,
    UXAuditSyncResponse,
)

router = APIRouter(prefix=f"{APIPath.V1}/uxaudit", tags=["uxaudit"])

# In-memory rate limit store and lock
_rate_limit = {
    "upload": {},
    "audit": {},
}
_rate_limit_lock = Lock()


def _audit_video_ux_background_task(user_email: str, file_name: str):
    """
    Background task wrapper for audit_video_ux to handle the tuple return value.
    """
    try:
        pdf_path, frames_analyzed = service.audit_video_ux(user_email, file_name)
        logger.info(
            f"Background UX audit completed. PDF: {pdf_path}, Frames: {frames_analyzed}"
        )
    except Exception as e:
        logger.error(f"Error in background UX audit task: {e}")


@router.post("/lead", response_model=GenericResponse)
async def audit_lead_ux(request: LeadUXAuditRequest):
    """
    Audit the UX of a lead.
    """
    return await service.send_lead_ux_audit_email(request.email)


@router.post("/audit", response_model=UXAuditResponse)
def audit_video_ux(
    request: UXAuditRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a UX audit for a video file in the background.
    Returns immediately with a confirmation message.
    """

    now = datetime.now(UTC)
    with _rate_limit_lock:
        last_upload = _rate_limit["audit"].get(request.email)
        if last_upload and now - last_upload < timedelta(hours=6):
            raise HTTPException(
                status_code=429, detail="You can only audit once every 6 hours."
            )
        _rate_limit["audit"][request.email] = now

    try:
        background_tasks.add_task(
            _audit_video_ux_background_task, request.email, request.key
        )
        return UXAuditResponse(
            message=f"UX audit started for file {request.key}", success=True
        )
    except Exception as e:
        logger.error(f"Error starting UX audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/audit/sync", response_model=UXAuditSyncResponse)
def audit_video_ux_sync(
    request: UXAuditRequest,
):
    """
    Perform a synchronous UX audit for a video file.
    Returns when the audit is complete with the PDF path.
    """
    try:
        logger.info(f"Starting synchronous UX audit for {request.key}")

        # Perform the audit synchronously
        pdf_path, frames_analyzed = service.audit_video_ux(request.email, request.key)

        return UXAuditSyncResponse(
            message=f"UX audit completed for file {request.key}",
            pdf_path=pdf_path,
            frames_analyzed=frames_analyzed,
            success=True,
        )
    except Exception as e:
        logger.error(f"Error performing synchronous UX audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=UploadResponse)
def upload_uxaudit_file(request: UploadRequest):
    """
    Generate a presigned S3 upload URL for a UX audit video file, rate-limited to one per email every 4 hours.
    """
    # Validate fileType
    if not request.fileType.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are allowed.")

    now = datetime.now(UTC)
    with _rate_limit_lock:
        last_upload = _rate_limit["upload"].get(request.email)
        if last_upload and now - last_upload < timedelta(hours=6):
            raise HTTPException(
                status_code=429, detail="You can only upload once every 6 hours."
            )
        _rate_limit["upload"][request.email] = now

    # S3 file path
    file_path = f"uxaudit/{request.email}/{request.fileName}"
    try:
        upload_url = s3_service.get_upload_url(file_path, request.fileType)
        return UploadResponse(
            upload_url=upload_url,
            file_path=file_path,
            message="Presigned upload URL generated successfully.",
            success=True,
        )
    except Exception as e:
        logger.error(f"Error generating presigned upload URL: {e}")
        raise HTTPException(status_code=500, detail="Could not generate upload URL.")
