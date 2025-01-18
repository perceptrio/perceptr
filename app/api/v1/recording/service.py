from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from schemas.recording_schema import RecordingUploadUrl, RecordingDownloadUrl
from common.services.s3 import s3_service
from common.services.logger import logger
from app.api.v1.org.service import get_org
from common.enums import RecordingType, VideoType

def validate_video_type(content_type: VideoType) -> None:
    """Validate that the content type is an allowed video format"""
    if content_type not in [t.value for t in VideoType]:
        logger.error(f"Invalid video type: {content_type}") 
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid video type"
        )

def validate_recording_type(recording_type: RecordingType) -> None:
    """Validate that the recording type is allowed"""
    if recording_type not in [t.value for t in RecordingType]:
        logger.error(f"Invalid recording type: {recording_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid recording type"
        )

def get_recording_upload_url(
    db: Session,
    recording_upload_url: RecordingUploadUrl
) -> str:
    """
    Generate a presigned URL for uploading a recording.
    
    Args:
        db: Database session
        org_id: Organization ID
        recording_id: Unique identifier for the recording
        content_type: MIME type of the video file
        recording_type: Type of recording (original or one_frame_per_second)
        expiration: URL expiration time in seconds (default: 1 hour)
    """
    # Verify org exists
    get_org(db, recording_upload_url.org_id)
    
    # Validate input parameters
    validate_video_type(recording_upload_url.content_type)
    validate_recording_type(recording_upload_url.recording_type)
    
    # Generate S3 path and URL
    file_path = f"{recording_upload_url.org_id}/recordings/{recording_upload_url.recording_id}/{recording_upload_url.recording_type}"
    return s3_service.get_upload_url(file_path, recording_upload_url.content_type, recording_upload_url.expiration)

def get_recording_download_url(
    db: Session,
    recording_download_url: RecordingDownloadUrl
) -> str:
    """
    Generate a presigned URL for downloading a recording.
    
    Args:
        db: Database session
        org_id: Organization ID
        recording_id: Unique identifier for the recording
        recording_type: Type of recording (original or one_frame_per_second)
        expiration: URL expiration time in seconds (default: 1 hour)
    """
    # Verify org exists
    get_org(db, recording_download_url.org_id)
    
    # Validate recording type
    validate_recording_type(recording_download_url.recording_type)
    
    # Generate S3 path and URL
    file_path = f"{recording_download_url.org_id}/recordings/{recording_download_url.recording_id}/{recording_download_url.recording_type}"
    return s3_service.get_download_url(file_path, recording_download_url.expiration)