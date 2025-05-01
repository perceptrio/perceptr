import uuid
from datetime import datetime, time
from typing import Any, Callable, List, Optional, Tuple, TypeVar, cast

import numpy as np
from api.v1.issue.repository import IssueRepository
from api.v1.issue_recording.repository import IssueRecordingRepository
from api.v1.org import service
from api.v1.recording_intervals import service as recording_intervals_service
from common.enums import AnalysisStatus, RecordingType, VideoType
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from fastapi import HTTPException, status
from graphs.issues_summarizer_graph import IssuesSummarizerGraph
from graphs.recording_analyzer_graph import RecordingAnalyzerGraph
from graphs.recording_summarizer_graph import RecordingSummarizerGraph
from graphs.video_recording_analyzer_graph import VideoRecordingAnalyzerGraph
from models.issue import Issue
from models.issue_recording import IssueRecording
from models.recording import Recording
from models.recording_interval import RecordingInterval
from sqlalchemy.orm import Session
from utils.recording import (
    extract_all_frames,
    extract_frames_at_timestamps,
    get_recording_duration,
    resize_frame,
)
from utils.rrweb import RRWebSessionUtils

from .repository import RecordingRepository
from .schema import (
    RecordingCreate,
    RecordingCreateForUpload,
    RecordingDownloadUrl,
    RecordingUploadUrl,
)

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
    file_path = f"{org_id}/recordings/{key}"
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
    file_path = f"{org_id}/recordings/{key}"
    upload_url = s3_service.get_upload_url(
        file_path,
        recording_upload_url.content_type,
        recording_upload_url.expiration,
    )
    return (upload_url, key)


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
    file_path = f"{org_id}/recordings/{recording_download_url.key}"
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
    s3_service.delete_folder(f"{org_id}/recordings/{recording.file_name.split('/')[0]}")
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


FRAMES_PER_SECOND = 1
FRAME_HEIGHT = 512
INTERVAL_DURATION = 30


def summarize_recording(
    org_id: int, recording_id: int, recording_intervals_summary: str
) -> Tuple[str, str]:
    graph = RecordingSummarizerGraph()
    summary_response = graph.summarize_recording(
        org_id, recording_id, recording_intervals_summary
    )
    return (
        summary_response["recording_summary"].summary,
        summary_response["recording_summary"].short_title,
    )


def format_timestamp(seconds: float) -> str:
    """Converts float seconds to HH:MM:SS format."""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        logger.warning(
            "Invalid timestamp encountered. Defaulting to 00:00:00",
            seconds=seconds,
        )
        return "00:00:00"
    # No need for math.modf if we just need HH:MM:SS
    total_seconds = int(round(seconds))  # Round to nearest second for HH:MM:SS
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def analyze_interval(
    org_id: int,
    recording_id: int,
    interval_frames: List[Tuple[str, np.ndarray, str]],
    should_resize_frame: bool = True,
) -> Tuple[List[RecordingInterval], str]:
    graph = RecordingAnalyzerGraph()

    if should_resize_frame:
        frames_for_graph = [
            (t, resize_frame(f, height=FRAME_HEIGHT), s) for t, f, s in interval_frames
        ]
    else:
        frames_for_graph = interval_frames

    interval_response = graph.analyze_recording(org_id, recording_id, frames_for_graph)
    recording_intervals_analysis = interval_response["recording_analysis"].intervals

    recording_interval_summary = interval_response["recording_analysis"].summary

    recording_intervals = []

    for recording_interval_analysis in recording_intervals_analysis:
        # Convert each TimestampDescription to JSON and then serialize the list
        timestamp_descriptions_json = [
            td.model_dump() for td in recording_interval_analysis.timestamp_descriptions
        ]

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

    return recording_intervals, recording_interval_summary


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
    analyzed_intervals: List[RecordingInterval],
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
    analyzed_recording_issues = []
    for interval in analyzed_intervals:
        if interval.category == "NORMAL":
            continue

        analyzed_recording_issues.append(
            {
                "recording_interval_id": interval.id,
                "issue": interval.issue,
                "category": interval.category,
            }
        )
    response = issues_summarizer_graph.aggregate_issues(
        org_id, recording_id, analyzed_recording_issues, existing_issues
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

        with FilesDownloader(s3_service.get_s3_client()) as downloader:
            local_recording_path = downloader.download_file_from_s3(
                f"{org_id}/recordings/{recording.file_name}"
            )

            analyze_local_recording_video(
                db, org_id, recording_id, recording, local_recording_path
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


def filter_frames(
    frames: List[Tuple[str, np.ndarray]], session: RRWebSessionUtils
) -> List[Tuple[str, np.ndarray]]:
    filtered_frames = []
    processed_events = session.process_events(save_events=True)
    logger.info(f"Stats: {processed_events['stats']}")
    # logger.info(f"Aggregated events: {processed_events['aggregated_events']}")
    for frame in frames:
        for event in processed_events["aggregated_events"]:
            if frame[0] == event["timestamp"]:
                filtered_frames.append(frame)
    return filtered_frames


@post_analysis_process()
def analyze_local_recording(
    db: Session,
    org_id: int,
    recording_id: int,
    recording: Recording,
    local_recording_path: str,
    session: RRWebSessionUtils,
) -> None:
    try:
        repository = RecordingRepository(db)
        issue_repository = IssueRepository(db)

        # Process events first to get timestamps
        processed_events = session.process_events(save_events=False)
        logger.info(f"Stats: {processed_events['stats']}")
        aggregated_events = processed_events.get("aggregated_events", [])

        # Get session start time in milliseconds (absolute)
        session_start_time_ms = session.get_start_time()
        if not isinstance(session_start_time_ms, int):
            # Fallback if start time is not an int (e.g. from JSONL parsing)
            if aggregated_events:
                session_start_time_ms = aggregated_events[0]["raw_timestamp_start"]
            else:
                session_start_time_ms = 0  # Or raise an error if no events

        # Extract absolute end timestamps (ms) for each aggregated second
        absolute_timestamps_ms = [
            event["raw_timestamp_end"] for event in aggregated_events
        ]

        # Calculate relative timestamps in seconds (for video frame extraction)
        relative_timestamps_sec = [
            (ts - session_start_time_ms) / 1000.0 for ts in absolute_timestamps_ms
        ]
        # Ensure timestamps are non-negative
        relative_timestamps_sec = [max(0, ts) for ts in relative_timestamps_sec]

        # Extract frames only at the specific relative timestamps
        # timestamped_frames will be List[Tuple[float, np.ndarray]]
        extracted_frames: List[Tuple[float, np.ndarray]] = extract_frames_at_timestamps(
            local_recording_path, relative_timestamps_sec
        )
        logger.info(
            f"Extracted {len(extracted_frames)} frames based on {len(relative_timestamps_sec)} event timestamps"
        )

        # Combine frames with their corresponding aggregated event summaries
        timestamped_frames_with_summary: List[Tuple[float, np.ndarray, str]] = []
        min_len = min(len(extracted_frames), len(aggregated_events))
        if len(extracted_frames) != len(aggregated_events):
            logger.warning(
                f"Recording {recording_id}: Mismatch in frame count ({len(extracted_frames)}) and aggregated event count ({len(aggregated_events)}). Using minimum length: {min_len}"
            )
        for i in range(min_len):
            timestamp, frame = extracted_frames[i]
            # Get summary, default to 'N/A' if missing
            summary = aggregated_events[i].get("summary", "N/A")
            timestamped_frames_with_summary.append((timestamp, frame, summary))

        # Get video duration
        if recording.file_duration is None:
            recording.file_duration = get_recording_duration(local_recording_path)
        video_duration = recording.file_duration or 0
        logger.info(
            f"Recording {recording_id}: Calculated video duration: {video_duration:.2f} seconds"
        )

        analyzed_intervals = []
        recording_intervals_summary = ""
        total_intervals = (
            (int(video_duration) // INTERVAL_DURATION)
            + (1 if video_duration % INTERVAL_DURATION > 0 else 0)
            if video_duration > 0
            else 1
        )

        # Iterate through time intervals (0-30s, 30-60s, etc.)
        for i in range(0, int(video_duration) + INTERVAL_DURATION, INTERVAL_DURATION):
            interval_start_time = i
            interval_end_time = i + INTERVAL_DURATION
            current_interval_idx = interval_start_time // INTERVAL_DURATION

            logger.info(
                f"Processing time interval {interval_start_time}s - {interval_end_time}s"
            )

            # Filter frames that belong to this time interval (timestamps are float seconds here)
            # Use the new structure: (float_timestamp, frame_data, summary)
            interval_frames_with_summary = [
                (ts, frame, summary)
                for ts, frame, summary in timestamped_frames_with_summary
                if interval_start_time <= ts < interval_end_time
            ]

            if not interval_frames_with_summary:
                logger.info(
                    f"No frames found for interval {interval_start_time}s - {interval_end_time}s"
                )
                # Update progress even if interval is empty
                progress = min(
                    round((current_interval_idx + 1) / total_intervals * 100, 2), 99.99
                )
                recording.analysis_progress = progress
                repository.update(recording)
                continue  # Skip analysis if no frames

            # Format timestamps to HH:MM:SS strings *before* calling analyze_interval
            # Prepare the List[Tuple[str, np.ndarray]] structure expected by analyze_interval
            formatted_interval_frames_for_analysis: List[
                Tuple[str, np.ndarray, str]
            ] = [
                (format_timestamp(ts_float), frame, summary)
                for ts_float, frame, summary in interval_frames_with_summary  # Ignore summary here
            ]

            # Log the formatted HH:MM:SS timestamps for this interval
            log_timestamps = [t for t, _, _ in formatted_interval_frames_for_analysis]
            logger.info(f"Frames within interval: {log_timestamps}")

            logger.info(
                f"Formatted interval frames for analysis: {formatted_interval_frames_for_analysis[0][2]}"
            )

            # Analyze the frames for this interval using the formatted timestamps
            analyzed_interval_data, recording_interval_summary = analyze_interval(
                org_id,
                recording_id,
                formatted_interval_frames_for_analysis,
                should_resize_frame=True,
            )

            summary_text = (
                f"Interval {format_timestamp(interval_start_time)} - {format_timestamp(interval_end_time - 0.001)} summary: "
                f"{recording_interval_summary}"
            )
            recording_intervals_summary += "\n" + summary_text

            # Update interval analysis progress
            progress = min(
                round((current_interval_idx + 1) / total_intervals * 100, 2), 99.99
            )
            recording.analysis_progress = progress
            repository.update(recording)

            analyzed_intervals.extend(analyzed_interval_data)

        has_intervals = (
            recording_intervals_service.check_recording_intervals_with_recording_id(
                db, recording_id
            )
        )
        if has_intervals:
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

        if recording_has_issues(analyzed_intervals):
            logger.info(f"Processing issues for recording {recording_id}")
            process_issues(db, org_id, recording_id, analyzed_intervals)
            issues = issue_repository.get_issues_by_recording(org_id, recording_id)
            categories = [issue.category for issue in issues]
            recording.tags = process_tags(categories)
            logger.info(f"Issues processed for recording {recording_id}")
        else:
            logger.info(f"No issues found for recording {recording_id}")

        # Update final recording state
        recording.summary = recording_summary
        recording.short_title = recording_short_title
        recording.set_analysis_status(AnalysisStatus.COMPLETED)
        recording.analysis_error = None
        recording.analysis_progress = 100
        repository.update(recording)

        logger.info(f"Analysis completed for recording {recording_id}")
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


@post_analysis_process()
def analyze_local_recording_video(
    db: Session,
    org_id: int,
    recording_id: int,
    recording: Recording,
    local_recording_path: str,
) -> None:
    """Analyzes a local video recording using VideoRecordingAnalyzerGraph."""
    try:
        repository = RecordingRepository(db)
        issue_repository = IssueRepository(db)

        # Get a fresh instance of the recording that's attached to the current session
        recording = repository.get_by_id(recording_id, org_id)
        if not recording:
            logger.error(f"Recording {recording_id} not found during analysis.")
            raise ValueError(f"Recording {recording_id} not found")

        # Set initial progress if desired
        # recording.analysis_progress = 10 # Example: Set to 10% before starting graph analysis
        # repository.update(recording)

        logger.info(
            f"Starting video analysis for recording {recording_id} using VideoRecordingAnalyzerGraph."
        )
        video_graph = VideoRecordingAnalyzerGraph()
        analysis_response = video_graph.analyze_recording(
            org_id=str(org_id),  # Ensure org_id is string if required by graph
            recording_id=str(recording_id),  # Ensure recording_id is string if required
            recording_path=local_recording_path,
            file_type=recording.file_type,
        )

        recording_analysis = analysis_response.get("recording_analysis")
        if not recording_analysis:
            raise ValueError(
                "Video analysis graph did not return the expected 'recording_analysis' structure."
            )

        # Extract analyzed intervals and summary from the graph response
        analyzed_intervals: List[RecordingInterval] = []
        # The graph returns Pydantic models, convert them to SQLAlchemy models if necessary
        # Assuming the structure matches:
        for interval_data in recording_analysis.intervals:
            # Convert TimestampDescription Pydantic models to JSON for storage,
            # formatting the timestamp within each description from MM:SS to HH:MM:SS
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
                    # Handle cases where the timestamp might not be in MM:SS format
                    logger.warning(
                        f"Could not parse timestamp '{ts_desc.timestamp}' for recording {recording_id}. Storing original."
                    )
                    processed_timestamp_descriptions_json.append(
                        ts_desc.model_dump()
                    )  # Store original if parsing fails

            # Convert MM:SS string from graph for start/end times to datetime.time object
            try:
                start_time_obj = datetime.strptime(
                    interval_data.start_time, "%M:%S"
                ).time()
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

            analyzed_intervals.append(
                RecordingInterval(
                    recording_id=recording_id,
                    start_time=start_time_obj,  # Use converted time object
                    end_time=end_time_obj,  # Use converted time object
                    category=interval_data.category,
                    issue=interval_data.issue,
                    short_title=interval_data.short_title,
                    timestamp_descriptions=processed_timestamp_descriptions_json,  # Use processed JSON list
                    description=interval_data.description,
                )
            )

        recording_summary = recording_analysis.summary
        # Assuming the graph summary is sufficient and we don't need a separate summarizer graph call
        # If a specific title format is needed, derive it or adjust the graph prompt

        logger.info(f"Video Analysis Summary: {recording_summary}")
        logger.info(f"Video Analysis Short Title: {recording_analysis.title}")

        # Persist intervals
        has_intervals = (
            recording_intervals_service.check_recording_intervals_with_recording_id(
                db, recording_id
            )
        )
        if has_intervals:
            logger.info(f"Replacing existing intervals for recording {recording_id}")
            recording_intervals_service.replace_recording_intervals(
                db, recording_id, analyzed_intervals
            )
        else:
            logger.info(f"Creating new intervals for recording {recording_id}")
            # Need to get IDs back if process_issues relies on interval IDs
            created_intervals = (
                recording_intervals_service.batch_create_recording_intervals(
                    db, analyzed_intervals
                )
            )
            # Assign created IDs back to analyzed_intervals if needed for process_issues
            # This depends on how batch_create returns IDs and if process_issues needs them.
            # For simplicity, assuming process_issues can work without explicit interval IDs for now.
            # If IDs are needed, adjust batch_create and the following process_issues call.

        # Process issues based on analyzed intervals
        if recording_has_issues(analyzed_intervals):
            logger.info(f"Processing issues for recording {recording_id}")
            # Ensure analyzed_intervals have IDs if process_issues requires them
            process_issues(db, org_id, recording_id, analyzed_intervals)
            issues = issue_repository.get_issues_by_recording(org_id, recording_id)
            categories = [issue.category for issue in issues]
            recording.tags = process_tags(categories)
            logger.info(f"Issues processed for recording {recording_id}")
        else:
            logger.info(f"No issues found for recording {recording_id}")

        # Update final recording state
        recording.summary = recording_summary
        recording.short_title = recording_analysis.title
        recording.set_analysis_status(AnalysisStatus.COMPLETED)
        recording.analysis_error = None
        recording.analysis_progress = 100
        # Potentially update file_duration if not already set and if determinable
        if recording.file_duration is None:
            try:
                recording.file_duration = get_recording_duration(local_recording_path)
            except Exception as dur_err:
                logger.warning(
                    f"Could not determine duration for {local_recording_path}: {dur_err}"
                )

        repository.update(recording)

        logger.info(f"Video analysis completed for recording {recording_id}")
        return None

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
