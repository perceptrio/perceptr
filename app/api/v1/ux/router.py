from api.v1.ux import service
from core.constants import APIPath
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from common.services.logger import logger
import os

from .schema import UXAuditRequest, UXAuditResponse, UXAuditSyncResponse

router = APIRouter(prefix=f"{APIPath.V1}/ux", tags=["ux"])


def _audit_video_ux_background_task(user_email: str, file_name: str):
    """
    Background task wrapper for audit_video_ux to handle the tuple return value.
    """
    try:
        pdf_path, frames_analyzed = service.audit_video_ux(user_email, file_name)
        logger.info(f"Background UX audit completed. PDF: {pdf_path}, Frames: {frames_analyzed}")
    except Exception as e:
        logger.error(f"Error in background UX audit task: {e}")


@router.post("/audit", response_model=UXAuditResponse)
def audit_video_ux(
    request: UXAuditRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a UX audit for a video file in the background.
    Returns immediately with a confirmation message.
    """
    try:
        background_tasks.add_task(
            _audit_video_ux_background_task, request.email, request.file_name
        )
        return UXAuditResponse(
            message=f"UX audit started for file {request.file_name}",
            success=True
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
        logger.info(f"Starting synchronous UX audit for {request.file_name}")
        
        # Perform the audit synchronously
        pdf_path, frames_analyzed = service.audit_video_ux(request.email, request.file_name)
        
        return UXAuditSyncResponse(
            message=f"UX audit completed for file {request.file_name}",
            pdf_path=pdf_path,
            frames_analyzed=frames_analyzed,
            success=True
        )
    except Exception as e:
        logger.error(f"Error performing synchronous UX audit: {e}")
        raise HTTPException(status_code=500, detail=str(e))
