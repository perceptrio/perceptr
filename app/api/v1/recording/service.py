from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.recording import Recording
from .schema import RecordingUploadUrl, RecordingDownloadUrl, RecordingCreate
from common.services.s3 import s3_service
from common.services.logger import logger
from api.v1.org import service
from common.enums import RecordingType, VideoType
from .repository import RecordingRepository
from graphs.recording_analyzer_graph import RecordingAnalyzerGraph
from utils.recording import preprocess_recording, timestamp_frames, resize_frame


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


def validate_recording_exists_in_s3(key: str, org_id: int) -> None:
    file_path = f"{org_id}/recordings/{key}"
    if not s3_service.check_file_exists(file_path):
        raise HTTPException(status_code=404, detail="Recording not uploaded")

def convert_video_type_to_extension(video_type: VideoType) -> str:
    return "." + video_type.split("/")[1]

def get_recording_upload_url(
    recording_name: str,
    org_id: int,
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
    service.get_org(db, org_id)
    
    # Validate input parameters
    validate_video_type(recording_upload_url.content_type)
    validate_recording_type(recording_upload_url.recording_type)
    
    # Generate S3 path and URL
    file_path = f"{org_id}/recordings/{recording_name}/{recording_upload_url.recording_type.value}{convert_video_type_to_extension(recording_upload_url.content_type)}"
    return s3_service.get_upload_url(file_path, recording_upload_url.content_type, recording_upload_url.expiration)

def get_recording_download_url(
    key: str,
    org_id: int,
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
    service.get_org(db, org_id)
     
    # Validate recording type
    validate_recording_type(recording_download_url.recording_type)
    
    # Generate S3 path and URL
    file_path = f"{org_id}/recordings/{key}"
    return s3_service.get_download_url(file_path, recording_download_url.expiration)

def create_recording(db: Session, org_id: int, recording: RecordingCreate) -> Recording:
    """Create a new recording"""
    # Verify org exists
    service.get_org(db, org_id)

    # Validate recording exists in S3
    validate_recording_exists_in_s3(recording.file_name, org_id)
    
    # Create recording
    repository = RecordingRepository(db)
    recording = repository.create(Recording(
        file_name=recording.file_name,
        file_size=recording.file_size,
        file_type=recording.file_type,
        org_id=org_id
    ))
    return recording

def get_recording(db: Session, recording_id: int, org_id: int) -> Recording:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )
    return recording

def get_recordings(db: Session, org_id: int, skip: int = 0, limit: int = 100) -> list[Recording]:
    repository = RecordingRepository(db)
    return repository.get_all(org_id, skip, limit)

def soft_delete_recording(db: Session, recording_id: int, org_id: int) -> None:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    repository.soft_delete(recording)
    

FRAMES_PER_SECOND = 1
RECORDINGS_PREFIX = "recordings/"
FRAME_HEIGHT = 512

def analyze_recording(user_id: str, recording_id: str, recording_path: str) -> dict:

    graph = RecordingAnalyzerGraph()
    recording_path = f"{RECORDINGS_PREFIX}/{recording_path}"
    preprocessed_recording_intervals = preprocess_recording(recording_path, frames_per_second=FRAMES_PER_SECOND)
    response = []
    # last_three_intervals = preprocessed_recording_intervals[-2:]
    for interval in preprocessed_recording_intervals:
        start_time, frames_with_times = interval
        print(f"Processing interval {start_time}")
        resized_frames = [(t, resize_frame(f, height=FRAME_HEIGHT)) for t, f in frames_with_times]
        timestamped_frames = timestamp_frames(resized_frames, start_time, FRAMES_PER_SECOND)
        interval_response = graph.analyze_recording(user_id, recording_id, recording_path, timestamped_frames)
        response.append(interval_response["recording_analysis"].json())

    return response