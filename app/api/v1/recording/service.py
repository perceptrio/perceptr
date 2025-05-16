import uuid
from datetime import datetime, time
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, cast
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from api.v1.issue.repository import IssueRepository
from api.v1.issue_recording.repository import IssueRecordingRepository
from api.v1.org import service
from api.v1.recording_intervals import service as recording_intervals_service
from common.enums import AnalysisStatus, RecordingType, VideoType
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from core.constants import SDK_FILE_EXTENSION
from fastapi import HTTPException, status
from graphs.issues_summarizer_graph import IssuesSummarizerGraph
from graphs.video_recording_analyzer_graph import VideoRecordingAnalyzerGraph
from graphs.recording_summarizer_graph import RecordingSummarizerGraph
from models.issue import Issue
from models.issue_recording import IssueRecording
from models.recording import Recording
from models.recording_interval import RecordingInterval
from sqlalchemy.orm import Session
from utils.recording import get_file_size, get_recording_duration, chunk_video, slow_down_video

from .repository import RecordingRepository
from .schema import (
    RecordingCreate,
    RecordingCreateForUpload,
    RecordingDownloadUrl,
    RecordingUploadUrl,
)
from settings import settings

# Type variables for the decorator
F = TypeVar("F", bound=Callable[..., Any])


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
        logger.error("Invalid video type", content_type=content_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid video type"
        )


def validate_recording_type(recording_type: RecordingType) -> None:
    """Validate that the recording type is allowed"""
    if recording_type not in [t.value for t in RecordingType]:
        logger.error("Invalid recording type", recording_type=recording_type)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid recording type"
        )


def validate_recording_exists_in_s3(key: str, org_id: int) -> None:
    file_path = f"{org_id}/{key}"
    if not s3_service.check_file_exists(file_path):
        raise HTTPException(status_code=404, detail="Recording not uploaded")


def convert_video_type_to_extension(video_type: VideoType) -> str:
    extension = video_type.split("/")[1]
    return "." + extension  # type: ignore


def get_recording_by_session_id(
    session_id: str, org_id: int, db: Session
) -> Optional[Recording]:
    repository = RecordingRepository(db)
    return repository.get_recording_by_session_id(session_id, org_id)


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
    extension = convert_video_type_to_extension(recording_upload_url.content_type)
    rec_type = recording_upload_url.recording_type.value
    key = f"{recording_name}/{rec_type}{extension}"
    file_path = f"{org_id}/{key}"
    upload_url = s3_service.get_upload_url(
        file_path,
        recording_upload_url.content_type,
        recording_upload_url.expiration,
    )
    return (upload_url, key)


def get_recording_download_type(recording_download_url: RecordingDownloadUrl) -> str:
    if recording_download_url.key.endswith(SDK_FILE_EXTENSION):
        return "sdk"
    else:
        return "video"


def get_recording_download_url(
    org_id: int, db: Session, recording_download_url: RecordingDownloadUrl
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

    # Generate S3 path and URL
    file_path = f"{org_id}/{recording_download_url.key}"
    download_url = s3_service.get_download_url(
        file_path, recording_download_url.expiration
    )
    return download_url  # type: ignore


def create_recording(db: Session, recording: RecordingCreate) -> Recording:
    """Create a new recording"""
    repository = RecordingRepository(db)
    recording_model = repository.create(
        Recording(
            file_name=recording.file_name,
            file_size=recording.file_size,
            file_type=recording.file_type,
            file_duration=recording.file_duration,
            org_id=recording.org_id,
            client_id=recording.client_id,
            client_data=recording.client_data,
            meta_data=recording.meta_data,
            analysis_status=recording.analysis_status,
            session_id=recording.session_id,
            short_title=recording.short_title,
            summary=recording.summary,
            tags=recording.tags,
        )
    )
    return recording_model


def update_recording(db: Session, recording: Recording) -> Recording:
    """Update a recording"""
    repository = RecordingRepository(db)
    recording = repository.update(recording)
    return recording


def create_recording_for_upload(
    db: Session, org_id: int, recording: RecordingCreateForUpload
) -> Recording:
    """Create a new recording for upload"""
    # Verify org exists
    service.get_org(db, org_id)

    # Validate recording exists in S3
    validate_recording_exists_in_s3(recording.file_name, org_id)

    # Create recording
    repository = RecordingRepository(db)
    recording_model = repository.create(
        Recording(
            file_name=recording.file_name,
            file_size=recording.file_size,
            file_type=recording.file_type,
            session_id=str(uuid.uuid4()),
            org_id=org_id,
        )
    )
    return recording_model


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
    search: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Recording]:
    repository = RecordingRepository(db)
    recordings = repository.get_all(org_id, skip, limit, search, start_date, end_date)
    return recordings


def get_stale_sessions(db: Session) -> List[Recording]:
    repository = RecordingRepository(db)
    recordings = repository.get_stale_sessions()
    return recordings


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
    s3_service.delete_folder(f"{org_id}/{recording.file_name.split('/')[0]}")
    repository.delete(recording)


def check_recording_belonging_to_org(
    db: Session, recording_id: int, org_id: int
) -> Recording:
    repository = RecordingRepository(db)
    recording = repository.get_by_id(recording_id, org_id)
    if not recording:
        raise HTTPException(
            status_code=404,
            detail="Recording not found, or does not belong to the organization",
        )
    return recording


def post_analysis_process(callback: Optional[Callable] = None) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        def wrapper(
            db: Session,
            org_id: int,
            recording_id: int,
            recording: Recording,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            result = func(db, org_id, recording_id, recording, *args, **kwargs)
            logger.info(
                "Analysis Process Completed for Recording",
                recording_id=recording_id,
                org_id=org_id,
            )
            return result

        return cast(F, wrapper)

    return decorator


def process_tags(categories: List[str]) -> str:
    tags = set(categories)
    tags.discard("NORMAL")

    if len(tags) == 0:
        return ""

    return ", ".join(tags)


def recording_has_issues(analyzed_intervals: List[RecordingInterval]) -> bool:
    for interval in analyzed_intervals:
        if interval.category != "NORMAL":
            return True
    return False


def process_issues(
    db: Session,
    org_id: int,
    recording_id: int,
    findings: List[Dict[str, Any]],
) -> None:
    issue_repository = IssueRepository(db)
    issue_recording_repository = IssueRecordingRepository(db)
    issues_summarizer_graph = IssuesSummarizerGraph()

    issues = issue_repository.get_all(org_id)
    existing_issues = []
    for issue_tuple in issues:
        issue = issue_tuple[0]  # Get the Issue object from the tuple
        existing_issues.append(
            {
                "issue_id": issue.id,
                "issue_description": issue.description,
                "issue_recommendation": issue.recommendation,
                "issue_severity": issue.severity,
                "issue_category": issue.category,
            }
        )

    response = issues_summarizer_graph.aggregate_issues(
        org_id, recording_id, findings, existing_issues
    )

    for aggregated_issue in response["aggregated_issues"].issues:
        if aggregated_issue.is_new_issue:
            issue = issue_repository.create(
                Issue(
                    org_id=org_id,
                    title=aggregated_issue.issue.issue_title,
                    description=aggregated_issue.issue.issue_description,
                    recommendation=aggregated_issue.issue.issue_recommendation,
                    severity=aggregated_issue.issue.issue_severity,
                    category=aggregated_issue.issue.issue_category,
                )
            )

            issue_recording_repository.create(
                IssueRecording(
                    org_id=org_id,
                    issue_id=issue.id,
                    recording_id=recording_id,
                    recording_interval_id=aggregated_issue.recording_interval_id,
                )
            )
        else:
            issue_recording_repository.create(
                IssueRecording(
                    org_id=org_id,
                    issue_id=aggregated_issue.issue.issue_id,
                    recording_id=recording_id,
                    recording_interval_id=aggregated_issue.recording_interval_id,
                )
            )


@post_analysis_process()
def analyze_recording(
    db: Session, org_id: int, recording_id: int, recording: Recording
) -> None:
    try:
        repository = RecordingRepository(db)

        # Get a fresh instance of the recording that's attached to the current session
        recording = repository.get_by_id(recording_id, org_id)
        if not recording:
            raise ValueError(f"Recording {recording_id} not found")
        recording.set_analysis_status(AnalysisStatus.IN_PROGRESS)
        repository.update(recording)
        with FilesDownloader(s3_service.get_s3_client()) as downloader:
            local_recording_path = downloader.download_file_from_s3(
                f"{org_id}/{recording.file_name}"
            )

            slowdown_factor = settings.SLOW_DOWN_FACTOR

            analyze_local_recording_video(
                db, org_id, recording_id, recording, local_recording_path, slowdown_factor=slowdown_factor
            )

        logger.info(
            "Analysis completed for recording",
            recording_id=recording_id,
            org_id=org_id,
        )
        return None

    except Exception as e:
        logger.error(
            "Error analyzing recording",
            recording_id=recording_id,
            org_id=org_id,
            exc_info=e,
        )
        # Get a fresh instance for error handling
        recording = repository.get_by_id(recording_id, org_id)
        if recording:
            recording.set_analysis_status(AnalysisStatus.FAILED)
            recording.analysis_error = str(e)
            repository.update(recording)
        return None


def process_intervals_findings(
    analyzed_intervals: List[RecordingInterval], timestamp_intervals
) -> List:
    all_findings = []
    for analyzed_interval, timestamp_interval in zip(
        analyzed_intervals, timestamp_intervals
    ):
        if analyzed_interval.category == "NORMAL":
            continue
        for finding in timestamp_interval.findings:
            all_findings.append(
                {
                    "recording_interval_id": analyzed_interval.id,
                    "description": finding.description,
                    "category": finding.category,
                }
            )

    return all_findings


@post_analysis_process()
def analyze_local_recording_video(
    db: Session,
    org_id: int,
    recording_id: int,
    recording: Recording,
    local_recording_path: str,
    slowdown_factor: float = 1.0,
) -> None:
    """
    Analyzes a local video recording using VideoRecordingAnalyzerGraph, breaking it into chunks.
    
    Args:
        db: Database session
        org_id: Organization ID
        recording_id: Recording ID
        recording: Recording model
        local_recording_path: Path to the local recording file
        slowdown_factor: Factor by which to slow down the video for analysis (e.g., 2.0 for half speed)
    """
    try:
        repository = RecordingRepository(db)
        issue_repository = IssueRepository(db)

        # Get a fresh instance of the recording that's attached to the current session
        recording = repository.get_by_id(recording_id, org_id)
        if not recording:
            logger.error(f"Recording {recording_id} not found during analysis.")
            raise ValueError(f"Recording {recording_id} not found")

        # Set initial progress
        recording.set_analysis_status(AnalysisStatus.IN_PROGRESS)
        recording.analysis_progress = 5
        repository.update(recording)

        logger.info(f"Starting video analysis for recording {recording_id} using VideoRecordingAnalyzerGraph.")
        
        # Check if FFmpeg is available
        try:
            from utils.recording import is_ffmpeg_available
            use_ffmpeg = is_ffmpeg_available()
            if use_ffmpeg:
                logger.info("FFmpeg detected - will use FFmpeg for video processing tasks")
            else:
                logger.warning("FFmpeg not found - will use OpenCV for video processing (slower)")
        except Exception:
            use_ffmpeg = False
            logger.warning("Error checking for FFmpeg - will use OpenCV for video processing")
        
        # Get total video duration of original video
        try:
            if use_ffmpeg:
                # Try FFmpeg first
                from utils.recording import ffmpeg_get_video_duration
                original_duration = ffmpeg_get_video_duration(local_recording_path)
                logger.info(f"Original video duration (FFmpeg): {original_duration} seconds for recording {recording_id}")
            else:
                # Use OpenCV
                original_duration = get_recording_duration(local_recording_path)
                logger.info(f"Original video duration (OpenCV): {original_duration} seconds for recording {recording_id}")
        except Exception as e:
            # Fall back to OpenCV
            logger.warning(f"Error getting duration with FFmpeg: {str(e)}")
            original_duration = get_recording_duration(local_recording_path)
            logger.info(f"Original video duration (OpenCV fallback): {original_duration} seconds for recording {recording_id}")
        
        # Create a slowed-down version of the video if requested
        slowed_video_path = local_recording_path
        if slowdown_factor > 1.0:
            logger.info(f"Slowing down entire video by factor of {slowdown_factor}x for analysis")
            
            # Create path for slowed video
            base_dir = os.path.dirname(local_recording_path)
            base_filename = os.path.basename(local_recording_path)
            name, ext = os.path.splitext(base_filename)
            slowed_video_path = os.path.join(base_dir, f"{name}_slowed{ext}")
            
            try:
                if use_ffmpeg:
                    # Try FFmpeg first for slowing down
                    from utils.recording import ffmpeg_slow_down_video
                    start_time = datetime.now()
                    ffmpeg_slow_down_video(local_recording_path, slowed_video_path, slowdown_factor)
                    elapsed = (datetime.now() - start_time).total_seconds()
                    logger.info(f"Created slowed version of video using FFmpeg at {slowed_video_path} in {elapsed:.1f}s")
                else:
                    raise RuntimeError("Using OpenCV for slowing down")
            except Exception as e:
                # Fall back to OpenCV
                logger.warning(f"FFmpeg slowing failed: {str(e)}. Falling back to OpenCV.")
                start_time = datetime.now()
                slow_down_video(local_recording_path, slowed_video_path, slowdown_factor)
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"Created slowed version of video using OpenCV at {slowed_video_path} in {elapsed:.1f}s")
            
            # Calculate the slowed duration for information
            try:
                if use_ffmpeg:
                    from utils.recording import ffmpeg_get_video_duration
                    slowed_duration = ffmpeg_get_video_duration(slowed_video_path)
                else:
                    slowed_duration = get_recording_duration(slowed_video_path)
            except:
                slowed_duration = get_recording_duration(slowed_video_path)
            logger.info(f"Slowed video duration: {slowed_duration} seconds (original: {original_duration} seconds)")
        
        # Initialize result containers
        all_intervals = []
        
        # Define chunk size in seconds for the slowed video
        slowed_chunk_size_seconds = settings.RECORDING_INTERVAL_DURATION
        
        # Split the slowed video into chunks
        logger.info(f"Splitting video into {slowed_chunk_size_seconds}-second chunks")
        try:
            if use_ffmpeg:
                # Try FFmpeg first for chunking
                from utils.recording import ffmpeg_chunk_video
                start_time = datetime.now()
                chunk_info = ffmpeg_chunk_video(slowed_video_path, slowed_chunk_size_seconds)
                elapsed = (datetime.now() - start_time).total_seconds()
                logger.info(f"Successfully split video into {len(chunk_info)} chunks using FFmpeg in {elapsed:.1f}s")
            else:
                raise RuntimeError("Using OpenCV for chunking")
        except Exception as e:
            # Fall back to OpenCV
            logger.warning(f"FFmpeg chunking failed: {str(e)}. Falling back to OpenCV.")
            start_time = datetime.now()
            chunk_info = chunk_video(slowed_video_path, slowed_chunk_size_seconds)
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"Successfully split video into {len(chunk_info)} chunks using OpenCV in {elapsed:.1f}s")
        
        chunk_count = len(chunk_info)
        
        video_graph = VideoRecordingAnalyzerGraph()
        
        try:
            # Initialize result containers for parallel processing
            max_workers = 5  # Maximum number of parallel tasks
            completed = 0
            
            logger.info(f"Starting parallel analysis of {chunk_count} chunks with max {max_workers} workers")
            
            # Process chunks in parallel with a maximum of 5 concurrent tasks
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all chunks for processing
                future_to_chunk = {}
                for i, (chunk_path, start_seconds, duration) in enumerate(chunk_info):
                    future = executor.submit(
                        analyze_video_chunk,
                        str(org_id),
                        str(recording_id),
                        chunk_path,
                        start_seconds,
                        recording.file_type,
                        video_graph,
                        slowdown_factor
                    )
                    future_to_chunk[future] = (i, chunk_path, start_seconds, duration)
                
                # Process results as they complete
                for future in as_completed(future_to_chunk):
                    i, chunk_path, start_seconds, duration = future_to_chunk[future]
                    completed += 1
                    
                    # Update progress
                    progress_pct = int(5 + (completed / chunk_count) * 70)  # 5-75% for chunking and analysis
                    recording.analysis_progress = progress_pct
                    repository.update(recording)
                    
                    try:
                        intervals, _, _ = future.result()
                        all_intervals.extend(intervals)
                        logger.info(f"Completed chunk {i+1}/{chunk_count} ({completed}/{chunk_count} done)")
                    except Exception as exc:
                        logger.error(f"Chunk {i+1} at {start_seconds}s generated an exception: {exc}")
                    
                    # Clean up chunk file
                    try:
                        os.remove(chunk_path)
                        logger.info(f"Removed chunk file after analysis: {chunk_path}")
                    except Exception as e:
                        logger.warning(f"Failed to remove chunk file {chunk_path}: {e}")
            
            # Clean up slowed video if it was created
            if slowed_video_path != local_recording_path:
                try:
                    os.remove(slowed_video_path)
                    logger.info(f"Removed slowed video file: {slowed_video_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove slowed video file {slowed_video_path}: {e}")
                    
            # Sort intervals by start time
            all_intervals.sort(key=lambda x: x.start_time)
            
            # Process the intervals
            logger.info(f"Processing analysis with {len(all_intervals)} intervals")
            
            # Convert the analysis to SQLAlchemy models
            analyzed_intervals: List[RecordingInterval] = []
            
            for interval_data in all_intervals:
                # Convert TimestampDescription models to JSON
                processed_timestamp_descriptions_json = []
                for ts_desc in interval_data.timestamp_descriptions:
                    try:
                        # Parse MM:SS string to time object
                        time_obj = datetime.strptime(ts_desc.timestamp, "%M:%S").time()
                        # Format time object to HH:MM:SS string
                        hhmmss_str = time_obj.strftime("%H:%M:%S")
                        # Dump original object and update the timestamp
                        ts_dict = ts_desc.model_dump()
                        ts_dict["timestamp"] = hhmmss_str
                        processed_timestamp_descriptions_json.append(ts_dict)
                    except ValueError:
                        logger.warning(
                            f"Could not parse timestamp '{ts_desc.timestamp}' for recording {recording_id}. Storing original."
                        )
                        processed_timestamp_descriptions_json.append(ts_desc.model_dump())

                # Convert MM:SS string to datetime.time object
                try:
                    start_time_obj = datetime.strptime(interval_data.start_time, "%M:%S").time()
                except ValueError:
                    logger.warning(
                        f"Could not parse start_time '{interval_data.start_time}' for recording {recording_id}. Defaulting to 00:00:00."
                    )
                    start_time_obj = time(0, 0, 0)
                try:
                    end_time_obj = datetime.strptime(interval_data.end_time, "%M:%S").time()
                except ValueError:
                    logger.warning(
                        f"Could not parse end_time '{interval_data.end_time}' for recording {recording_id}. Defaulting to 00:00:00."
                    )
                    end_time_obj = time(0, 0, 0)

                findings = interval_data.findings
                if findings and len(findings) > 0:
                    category = findings[0].category if len(findings) > 0 else "BUG"
                    issue = ""
                else:
                    category = "NORMAL"
                    issue = None

                analyzed_intervals.append(
                    RecordingInterval(
                        recording_id=recording_id,
                        start_time=start_time_obj,
                        end_time=end_time_obj,
                        category=category,
                        issue=issue,
                        short_title=interval_data.short_title,
                        timestamp_descriptions=processed_timestamp_descriptions_json,
                        description=interval_data.description,
                    )
                )
            
            # Persist intervals
            recording.analysis_progress = 90
            repository.update(recording)
            
            has_intervals = recording_intervals_service.check_recording_intervals_with_recording_id(
                db, recording_id
            )
            if has_intervals:
                logger.info(f"Replacing existing intervals for recording {recording_id}")
                recording_intervals_service.replace_recording_intervals(
                    db, recording_id, analyzed_intervals
                )
            else:
                logger.info(f"Creating new intervals for recording {recording_id}")
                created_intervals = recording_intervals_service.batch_create_recording_intervals(
                    db, analyzed_intervals
                )
            
            # Process issues
            if recording_has_issues(analyzed_intervals):
                logger.info(f"Processing issues for recording {recording_id}")
                all_findings = process_intervals_findings(analyzed_intervals, all_intervals)
                process_issues(db, org_id, recording_id, all_findings)
                issues = issue_repository.get_issues_by_recording(org_id, recording_id)
                categories = [issue.category for issue in issues]
                recording.tags = process_tags(categories)
                logger.info(f"Issues processed for recording {recording_id}")
            else:
                logger.info(f"No issues found for recording {recording_id}")
            
            # Use the RecordingSummarizerGraph to generate the recording summary and title
            logger.info(f"Generating summary and title for recording {recording_id}")
            recording_summarizer = RecordingSummarizerGraph()
            
            # Create a detailed summary of all intervals for the summarizer
            intervals_summary = []
            for interval in analyzed_intervals:
                interval_summary = f"Interval from {interval.start_time} to {interval.end_time}: {interval.short_title}\n"
                interval_summary += f"Description: {interval.description}\n"
                if interval.category != "NORMAL":
                    interval_summary += f"Category: {interval.category}\n"
                interval_summary += "---\n"
                intervals_summary.append(interval_summary)
            
            full_intervals_summary = "\n".join(intervals_summary)
            full_intervals_summary += f"\nTotal recording duration: {original_duration:.2f} seconds."
            
            # Call the recording summarizer graph
            summary_response = recording_summarizer.summarize_recording(
                org_id=str(org_id),
                recording_id=str(recording_id),
                recording_intervals_summary=full_intervals_summary
            )
            
            recording_summary = summary_response.get("recording_summary")
            
            # Update final recording state
            recording.summary = recording_summary.summary if recording_summary else full_intervals_summary
            recording.short_title = recording_summary.short_title if recording_summary else f"Chunked Analysis of Recording {recording_id}"
            recording.set_analysis_status(AnalysisStatus.COMPLETED)
            recording.analysis_error = None
            recording.analysis_progress = 100
            
            # Update file metadata if not already set
            if recording.file_duration is None:
                recording.file_duration = original_duration
            
            recording.file_size = get_file_size(local_recording_path)
            repository.update(recording)
            
            logger.info(f"Chunked video analysis completed for recording {recording_id}")
            return None
            
        finally:
            # Clean up any remaining chunk files
            logger.info(f"Cleaning up any remaining chunk files")
            for _, (chunk_path, _, _) in enumerate(chunk_info):
                if os.path.exists(chunk_path):
                    try:
                        os.remove(chunk_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove chunk file {chunk_path}: {e}")

    except Exception as e:
        logger.error(
            "Error analyzing video recording",
            recording_id=recording_id,
            org_id=org_id,
            exc_info=e,
        )
        # Ensure repository is defined in exception block scope if needed
        try:
            recording_repo_on_error = RecordingRepository(db)
            recording_on_error = recording_repo_on_error.get_by_id(recording_id, org_id)
            if recording_on_error:
                recording_on_error.set_analysis_status(AnalysisStatus.FAILED)
                recording_on_error.analysis_error = str(e)
                recording_repo_on_error.update(recording_on_error)
        except Exception as update_err:
            logger.error(
                f"Failed to update recording status to FAILED for {recording_id}",
                org_id=org_id,
                recording_id=recording_id,
                exc_info=update_err,
            )
        return None

def analyze_video_chunk(
    org_id: str,
    recording_id: str,
    chunk_path: str,
    start_seconds: float,
    file_type: str,
    video_graph: VideoRecordingAnalyzerGraph,
    slowdown_factor: float = 1.0
) -> Tuple[List[Any], float, float]:
    """
    Analyze a single video chunk and adjust timestamps.
    
    Args:
        org_id: Organization ID
        recording_id: Recording ID
        chunk_path: Path to the chunk file
        start_seconds: Start time of the chunk in slowed video (seconds)
        file_type: File type of the video
        video_graph: Initialized VideoRecordingAnalyzerGraph instance
        slowdown_factor: Factor by which the video has been slowed down
        
    Returns:
        Tuple containing (intervals, start_seconds, duration)
    """
    chunk_id = f"{recording_id}_chunk_{start_seconds}"
    slowed_duration = 0
    
    # Get the duration of the chunk (already slowed)
    try:
        slowed_duration = get_recording_duration(chunk_path)
        logger.info(f"Analyzing chunk starting at {start_seconds}s (slowed time) - Slowed duration: {slowed_duration:.2f}s")
    except Exception as e:
        logger.warning(f"Could not determine duration for chunk {chunk_path}: {e}")
    
    # Analyze the chunk with AI
    logger.info(f"Running AI analysis on chunk {chunk_id} (from slowed video)")
    chunk_analysis = video_graph.analyze_recording(
        org_id=str(org_id),
        recording_id=chunk_id,
        recording_path=chunk_path,
        file_type=file_type,
    )
    
    # Process and adjust timestamps
    chunk_recording_analysis = chunk_analysis.get("recording_analysis")
    intervals = []
    
    if chunk_recording_analysis:
        # Helper functions for time conversion
        def time_to_seconds(time_str):
            parts = time_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        
        def seconds_to_time(seconds):
            return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"
        
        interval_count = len(chunk_recording_analysis.intervals)
        logger.info(f"AI found {interval_count} intervals in the chunk - now adjusting timestamps")
        
        # Adjust timestamps to account for slowdown
        for i, interval in enumerate(chunk_recording_analysis.intervals):
            # Get slowed timestamps (as analyzed by AI)
            slowed_start_seconds = time_to_seconds(interval.start_time)
            slowed_end_seconds = time_to_seconds(interval.end_time)
            
            # Calculate original (real-time) positions
            # 1. Convert relative chunk time to absolute slowed video time
            absolute_slowed_start = slowed_start_seconds + start_seconds
            absolute_slowed_end = slowed_end_seconds + start_seconds
            
            # 2. Convert slowed time to original time 
            original_start_seconds = absolute_slowed_start / slowdown_factor
            original_end_seconds = absolute_slowed_end / slowdown_factor
            
            # Update with adjusted timestamps
            interval.start_time = seconds_to_time(original_start_seconds)
            interval.end_time = seconds_to_time(original_end_seconds)
            
            # Adjust timestamps in descriptions
            timestamp_count = len(interval.timestamp_descriptions)
            for j, desc in enumerate(interval.timestamp_descriptions):
                # Get slowed timestamp
                slowed_ts_seconds = time_to_seconds(desc.timestamp)
                
                # Convert to absolute slowed time
                absolute_slowed_ts = slowed_ts_seconds + start_seconds
                
                # Convert to original time
                original_ts_seconds = absolute_slowed_ts / slowdown_factor
                
                
                # Update the timestamp
                desc.timestamp = seconds_to_time(original_ts_seconds)
        
        intervals = chunk_recording_analysis.intervals
        
        # Process each interval to consolidate timestamp descriptions
        for interval in intervals:
            try:
                if hasattr(interval, 'timestamp_descriptions') and interval.timestamp_descriptions:
                    # Extract the timestamp descriptions list
                    ts_descriptions = interval.timestamp_descriptions
                    
                    # Skip if empty
                    if not ts_descriptions:
                        continue
                    
                    # Check if they're already dictionaries or need conversion
                    ts_dict_list = []
                    original_type = None
                    
                    try:
                        if hasattr(ts_descriptions[0], 'model_dump'):
                            # Save the original type for later conversion back
                            original_type = type(ts_descriptions[0])
                            # Convert Pydantic models to dictionaries
                            ts_dict_list = [ts.model_dump() for ts in ts_descriptions]
                        else:
                            # Already dictionaries
                            ts_dict_list = ts_descriptions
                    except (IndexError, AttributeError):
                        # Handle case where ts_descriptions is empty or doesn't have expected methods
                        logger.warning(f"Could not process timestamp descriptions - index error or attribute error")
                        continue
                    
                    # Skip if no valid descriptions after conversion
                    if not ts_dict_list:
                        continue
                    
                    # Consolidate timestamp descriptions
                    logger.info(f"Consolidating {len(ts_dict_list)} timestamp descriptions...")
                    consolidated_descriptions = consolidate_timestamp_descriptions(ts_dict_list)
                    logger.info(f"Consolidated to {len(consolidated_descriptions)} unique timestamps")
                    
                    # Update the interval with consolidated descriptions only if we got valid results
                    if consolidated_descriptions:
                        # If we originally had Pydantic models, convert back to the same type
                        if original_type and hasattr(original_type, 'model_validate'):
                            try:
                                # Convert dictionaries back to the original Pydantic model
                                converted_descriptions = [
                                    original_type.model_validate(desc) 
                                    for desc in consolidated_descriptions
                                ]
                                interval.timestamp_descriptions = converted_descriptions
                            except Exception as e:
                                logger.error(f"Error converting back to Pydantic model: {str(e)}")
                                # Fall back to using dictionaries
                                interval.timestamp_descriptions = consolidated_descriptions
                        else:
                            # Use dictionaries directly
                            interval.timestamp_descriptions = consolidated_descriptions
            except Exception as e:
                # Log error but continue processing other intervals
                logger.error(f"Error processing timestamp descriptions: {str(e)}")
                continue
        
        logger.info(f"Successfully adjusted timestamps for {interval_count} intervals from chunk {chunk_id}")
    else:
        logger.warning(f"No intervals found in chunk {chunk_id}")
    
    # Calculate original start time and duration
    original_start_seconds = start_seconds / slowdown_factor
    original_duration = slowed_duration / slowdown_factor
    
    # Return the adjusted intervals and original timing info
    return intervals, original_start_seconds, original_duration

def consolidate_timestamp_descriptions(timestamp_descriptions: list, time_threshold_seconds: int = 1) -> list:
    """
    Process timestamp descriptions to merge duplicate entries and similar descriptions
    that appear at the same timestamp.
    
    Args:
        timestamp_descriptions: List of timestamp description objects 
        time_threshold_seconds: Not used anymore - kept for backwards compatibility
        
    Returns:
        List of processed timestamp descriptions with duplicates consolidated
    """
    if not timestamp_descriptions:
        return []
    
    try:
        # Step 1: Standardize the input format and extract timestamps + descriptions
        standardized_descriptions = []
        
        for item in timestamp_descriptions:
            # Skip invalid entries
            if not isinstance(item, dict):
                continue
                
            timestamp = item.get("timestamp")
            description = item.get("description")
            
            if not timestamp or not description:
                continue
                
            standardized_descriptions.append({
                "timestamp": timestamp,
                "description": description
            })
        
        if not standardized_descriptions:
            return timestamp_descriptions  # Return original if no valid items
            
        # Step 2: Group by timestamp (exact match)
        timestamp_groups = {}
        for item in standardized_descriptions:
            ts = item["timestamp"]
            if ts not in timestamp_groups:
                timestamp_groups[ts] = []
            timestamp_groups[ts].append(item["description"])
            
        # Step 3: Generate consolidated output
        consolidated = []
        for timestamp, descriptions in sorted(timestamp_groups.items()):
            # If only one description for this timestamp, keep as is
            if len(descriptions) == 1:
                consolidated.append({
                    "timestamp": timestamp,
                    "description": descriptions[0]
                })
                continue
                
            # Remove exact duplicates first
            unique_descriptions = []
            for desc in descriptions:
                if desc not in unique_descriptions:
                    unique_descriptions.append(desc)
                    
            # If we've reduced to one description, add it and continue
            if len(unique_descriptions) == 1:
                consolidated.append({
                    "timestamp": timestamp,
                    "description": unique_descriptions[0]
                })
                continue
                
            # Multiple different descriptions: combine them with a separator
            # For production, you might want more sophisticated similarity checks here
            combined = " ".join(unique_descriptions)
            consolidated.append({
                "timestamp": timestamp,
                "description": combined
            })
            
        return consolidated
            
    except Exception as e:
        import traceback
        print(f"Error consolidating timestamp descriptions: {e}")
        print(traceback.format_exc())
        return timestamp_descriptions  # Return original data on error
