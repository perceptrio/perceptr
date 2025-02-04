from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.recording import Recording
from .schema import RecordingUploadUrl, RecordingDownloadUrl, RecordingCreate
from common.services.s3 import s3_service
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from api.v1.org import service
from common.enums import RecordingType, VideoType
from .repository import RecordingRepository
from graphs.recording_analyzer_graph import RecordingAnalyzerGraph
from graphs.recording_summarizer_graph import RecordingSummarizerGraph
from utils.recording import resize_frame, extract_all_frames, get_recording_duration
from models.recording_interval import RecordingInterval
from api.v1.recording_intervals import service as recording_intervals_service
import json
from common.enums import AnalysisStatus
from typing import List, Tuple
import numpy as np
from datetime import datetime


def convert_model_to_schema(recording: Recording) -> Recording:
    return Recording(
        id=recording.id,
        file_name=recording.file_name,
        file_size=recording.file_size,
        file_type=recording.file_type,
        org_id=recording.org_id,
        created_at=recording.created_at,
        updated_at=recording.updated_at,
        deleted_at=recording.deleted_at,
        analysis_status=recording.analysis_status,
        analysis_error=recording.analysis_error,
    )


def validate_video_type(content_type: VideoType) -> None:
    """Validate that the content type is an allowed video format"""
    if content_type not in [t.value for t in VideoType]:
        logger.error(f"Invalid video type: {content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid video type"
        )


def validate_recording_type(recording_type: RecordingType) -> None:
    """Validate that the recording type is allowed"""
    if recording_type not in [t.value for t in RecordingType]:
        logger.error(f"Invalid recording type: {recording_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid recording type"
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
    recording_upload_url: RecordingUploadUrl,
) -> Tuple[str, str]:
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
    key = f"{recording_name}/{recording_upload_url.recording_type.value}{convert_video_type_to_extension(recording_upload_url.content_type)}"
    file_path = f"{org_id}/recordings/{key}"
    return (
        s3_service.get_upload_url(
            file_path,
            recording_upload_url.content_type,
            recording_upload_url.expiration,
        ),
        key,
    )


def get_recording_download_url(
    key: str, org_id: int, db: Session, recording_download_url: RecordingDownloadUrl
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
    recording = repository.create(
        Recording(
            file_name=recording.file_name,
            file_size=recording.file_size,
            file_type=recording.file_type,
            org_id=org_id,
        )
    )
    return recording


def get_recording(db: Session, recording_id: int, org_id: int) -> Recording:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found"
        )
    return recording


def get_recordings(
    db: Session,
    org_id: int,
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
) -> list[Recording]:
    repository = RecordingRepository(db)
    return repository.get_all(org_id, skip, limit, search, start_date, end_date)


def soft_delete_recording(db: Session, recording_id: int, org_id: int) -> None:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    repository.soft_delete(recording)


def hard_delete_recording(db: Session, recording_id: int, org_id: int) -> None:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(status_code=404, detail="Recording not found")
    s3_service.delete_folder(f"{org_id}/recordings/{recording.file_name}")
    repository.delete(recording)


def check_recording_belonging_to_org(
    db: Session, recording_id: int, org_id: int
) -> None:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(
            status_code=404,
            detail="Recording not found, or does not belong to the organization",
        )
    return recording


def post_analysis_process(callback=None):
    def decorator(func):
        def wrapper(
            db: Session,
            org_id: int,
            recording_id: int,
            recording: Recording,
            *args,
            **kwargs,
        ):
            result = func(db, org_id, recording_id, recording, *args, **kwargs)
            logger.info(f"Analysis Process Completed - Recording: {recording_id}")
            return result

        return wrapper

    return decorator


FRAMES_PER_SECOND = 1
FRAME_HEIGHT = 512
INTERVAL_DURATION = 30


def summarize_recording(
    org_id: int, recording_id: int, recording_intervals_summary: str
):
    graph = RecordingSummarizerGraph()
    summary_response = graph.summarize_recording(
        org_id, recording_id, recording_intervals_summary
    )
    return (
        summary_response["recording_summary"].summary,
        summary_response["recording_summary"].short_title,
    )


def analyze_interval(
    org_id: int, recording_id: int, interval_frames: List[Tuple[str, np.ndarray]]
):
    graph = RecordingAnalyzerGraph()
    resized_frames = [
        (t, resize_frame(f, height=FRAME_HEIGHT)) for t, f in interval_frames
    ]
    interval_response = graph.analyze_recording(org_id, recording_id, resized_frames)
    recording_intervals_analysis = interval_response["recording_analysis"].intervals

    recording_interval_summary = interval_response["recording_analysis"].summary

    recording_intervals = []

    categories = [
        interval_analysis.category for interval_analysis in recording_intervals_analysis
    ]

    for recording_interval_analysis in recording_intervals_analysis:
        # Convert each TimestampDescription to JSON and then serialize the list
        timestamp_descriptions_json = json.dumps(
            [td.json() for td in recording_interval_analysis.timestamp_descriptions]
        )

        recording_interval = RecordingInterval(
            recording_id=recording_id,
            start_time=recording_interval_analysis.start_time,
            end_time=recording_interval_analysis.end_time,
            category=recording_interval_analysis.category,
            issue=recording_interval_analysis.issue,
            short_title=recording_interval_analysis.short_title,
            timestamp_descriptions=timestamp_descriptions_json,
            description=recording_interval_analysis.description,
        )

        recording_intervals.append(recording_interval)

    return recording_intervals, recording_interval_summary, categories


def process_tags(categories: List[str]) -> str:
    tags = set(categories)
    tags.discard("NORMAL")

    if len(tags) == 0:
        return ""

    return ", ".join(tags)


@post_analysis_process()
def analyze_recording(
    db: Session, org_id: int, recording_id: int, recording: Recording
) -> dict:
    try:
        repository = RecordingRepository(db)
        # Get a fresh instance of the recording that's attached to the current session
        recording = repository.get_by_id(recording_id, org_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found")

        with FilesDownloader(s3_service.get_s3_client()) as downloader:
            local_recording_path = downloader.download_file_from_s3(
                f"{org_id}/recordings/{recording.file_name}"
            )

            timestamped_frames = extract_all_frames(
                local_recording_path, FRAMES_PER_SECOND
            )
            print(f"Extracted {len(timestamped_frames)} frames from video")

            if recording.file_duration is None:
                recording.file_duration = get_recording_duration(local_recording_path)

            analyzed_intervals = []
            recording_intervals_summary = ""
            categories = []
            for i in range(0, len(timestamped_frames), INTERVAL_DURATION):
                interval_frames = timestamped_frames[i : i + INTERVAL_DURATION]
                timestamps = [t for t, _ in interval_frames]
                print(f"Processing interval {timestamps}")
                recording_intervals, recording_interval_summary, categories = (
                    analyze_interval(org_id, recording_id, interval_frames)
                )
                recording_interval_summary = f"Interval {timestamps[0]} - {timestamps[-1]} summary: {recording_interval_summary}"
                recording_intervals_summary += "\n" + recording_interval_summary
                categories.extend(categories)
                # Update recording progress
                recording.analysis_progress = i / len(timestamped_frames) * 100
                repository.update(recording)
                analyzed_intervals.extend(recording_intervals)

            if recording_intervals_service.check_recording_intervals_with_recording_id(
                db, recording_id
            ):
                recording_intervals_service.replace_recording_intervals(
                    db, recording_id, analyzed_intervals
                )
            else:
                recording_intervals_service.batch_create_recording_intervals(
                    db, analyzed_intervals
                )

        logger.info(f"Summarizing recording {recording_id}")
        recording_summary, recording_short_title = summarize_recording(
            org_id, recording_id, recording_intervals_summary
        )
        logger.info(f"Recording summary: {recording_summary}")
        logger.info(f"Recording short title: {recording_short_title}")

        # Update final recording state
        recording.summary = recording_summary
        recording.short_title = recording_short_title
        recording.set_analysis_status(AnalysisStatus.COMPLETED)
        recording.analysis_error = None
        recording.analysis_progress = 100
        recording.tags = process_tags(categories)
        repository.update(recording)

        logger.info(f"Analysis completed for recording {recording_id}")
        return

    except Exception as e:
        logger.error(
            "Error analyzing recording", recording_id=recording_id, error=str(e)
        )
        # Get a fresh instance for error handling
        recording = repository.get_by_id(recording_id, org_id)
        if recording:
            recording.set_analysis_status(AnalysisStatus.FAILED)
            recording.analysis_error = str(e)
            repository.update(recording)
        return
