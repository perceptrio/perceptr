import gzip
import io
import time
from datetime import UTC, datetime, timedelta

from api.v1.recording import service as recording_service
from api.v1.recording.schema import RecordingCreate
from common.enums import AnalysisStatus, VideoType
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from core.constants import SDK_FILE_EXTENSION
from fastapi import BackgroundTasks
from models.recording import Recording
from settings import settings
from sqlalchemy.orm import Session
from utils.rrweb import RRWebSessionUtils, merge_rrweb_batches


def _compress_content(content: str) -> bytes:
    """Compress content using gzip"""
    compressed_content = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed_content, mode="wb") as f:
        f.write(content.encode("utf-8"))
    return compressed_content.getvalue()


def get_or_create_recording_from_session(
    db: Session, org_id: int, session_id: str, force: bool = False
) -> Recording:
    # First check if recording already exists for this session
    existing_recording = recording_service.get_recording_by_session_id(
        session_id, org_id, db
    )

    if existing_recording:
        if (
            existing_recording.analysis_status != AnalysisStatus.PENDING.value
            and existing_recording.analysis_status != AnalysisStatus.FAILED.value
            and not force
        ):
            return {
                "success": True,
                "message": f"Session already processed",
            }

        # If recording exists, use it
        recording = existing_recording
        logger.info(
            "Using existing recording",
            session_id=session_id,
            org_id=org_id,
            recording_id=recording.id,
        )
        return recording
    else:
        # Create new recording if none exists
        """Create a recording from a session"""
        recordingCreate = RecordingCreate(
            org_id=org_id,
            session_id=session_id,
            file_name=f"{session_id}/{SDK_FILE_EXTENSION}",
            file_type=VideoType.WEBM.value,
            file_size=0,
            analysis_status=AnalysisStatus.IN_PROGRESS.value,
        )
        return recording_service.create_recording(db, recordingCreate)


def _process_session_background(
    db: Session,
    org_id: int,
    session_id: str,
    force: bool = False,
) -> None:
    """Background task to process a session"""
    recording = recording_service.get_recording_by_session_id(session_id, org_id, db)
    if not recording:
        logger.error(
            "Recording not found while processing session",
            session_id=session_id,
            org_id=org_id,
        )
        return
    if recording.analysis_status != AnalysisStatus.PENDING.value and not force:
        logger.info(
            "Skipping analysis for non-pending session",
            session_id=session_id,
            org_id=org_id,
        )
        return
    try:
        logger.info(
            "Processing session started",
            session_id=recording.session_id,
            org_id=org_id,
            recording_id=recording.id,
        )

        # Download the session batches
        with FilesDownloader(
            s3_service.get_s3_client(), keep_temp_dir=False
        ) as downloader:
            session_prefix = f"{org_id}/{session_id}/"
            local_file_paths = downloader.download_all_session_batches(session_prefix)
            logger.info(
                "Session files downloaded",
                session_id=session_id,
                file_count=len(local_file_paths),
            )

            # Process the files
            merged_file_path = merge_rrweb_batches(local_file_paths)
            logger.info(
                "Files merged successfully",
                session_id=session_id,
                output_path=merged_file_path,
            )

            # Upload the merged file to S3
            s3_path = f"{org_id}/{session_id}/{SDK_FILE_EXTENSION}"
            with open(merged_file_path, "rb") as f:
                content = f.read()
                # Decode bytes to string before compression
                content_str = content.decode("utf-8")
                compressed_content = _compress_content(content_str)
                s3_service.upload_file(s3_path, compressed_content)

            session = RRWebSessionUtils(merged_file_path)

            # Print session summary
            logger.info(
                "Session summary",
                session_id=session_id,
                summary=session.get_session_summary(),
                start_time=session.get_start_time(),
                end_time=session.get_end_time(),
                duration=session.get_duration(),
                event_count=len(session.get_events()),
                user_identity=session.get_user_identity(),
            )

            # Skip sessions with 0 duration
            if session.get_duration() == "00:00:00":
                logger.info(
                    "Skipping analysis for zero duration session", session_id=session_id
                )
                return

            # Convert to video
            logger.info("Starting video conversion", session_id=session_id)
            result = session.convert_events_to_video()

            if result["success"]:
                logger.info(
                    "Video conversion successful",
                    session_id=session_id,
                    output_path=result["output_path"],
                )
                if settings.AI_ANALYSIS_ENABLED:
                    recording_service.analyze_local_recording_video(
                        db, org_id, recording.id, recording, result["output_path"]
                    )
                else:
                    logger.info(
                        "AI analysis skipped - disabled in settings",
                        session_id=session_id,
                    )
            else:
                error_msg = result.get("error", result.get("message", "Unknown error"))
                logger.error(
                    "Video conversion failed", session_id=session_id, error=error_msg
                )
                raise Exception(f"Video conversion failed: {error_msg}")

    except Exception as e:
        logger.error(
            "Error processing session",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
            recording_id=recording.id,
        )
        recording = recording_service.get_recording(db, recording.id, org_id)
        recording.analysis_status = AnalysisStatus.FAILED.value
        recording.analysis_error = str(e)
        recording_service.update_recording(db, recording)


def process_session(
    db: Session,
    org_id: int,
    session_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    """Process a session"""
    try:
        background_tasks.add_task(
            _process_session_background, db, org_id, session_id, force
        )

        return {"success": True, "message": "Session scheduled for processing"}
    except Exception as e:
        logger.error(
            "Error processing session",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
        )
        raise


def upsert_session_for_batch(db: Session, org_id: int, session_id: str) -> Recording:
    """Upsert a recording for batch upload: create if not exist, else update updated_at only."""

    recording = recording_service.get_recording_by_session_id(session_id, org_id, db)
    if recording:
        recording.updated_at = datetime.now(UTC)
        recording_service.update_recording(db, recording)
        return recording
    else:
        recording_create = RecordingCreate(
            org_id=org_id,
            session_id=session_id,
            file_name=f"{session_id}/{SDK_FILE_EXTENSION}",
            file_type=VideoType.WEBM.value,
            file_size=0,
            analysis_status=AnalysisStatus.PENDING.value,
        )
        return recording_service.create_recording(db, recording_create)


def check_and_process_stale_recording(db: Session, org_id: int, session_id: str):
    """Background task that waits 1 hour, then checks if the recording is still not processed and updated_at > 1 hour ago, and if so, triggers processing."""
    time.sleep(settings.STALE_SESSION_DURATION)
    recording = recording_service.get_recording_by_session_id(session_id, org_id, db)
    if not recording:
        # TODO: maybe add a cleaner to delete stale batches in s3?
        return
    # Use UTC for comparison
    now = datetime.now(UTC)
    if recording.analysis_status == AnalysisStatus.PENDING.value and (
        now - recording.updated_at
    ) > timedelta(seconds=settings.STALE_SESSION_DURATION):
        # Trigger processing
        _process_session_background(db, org_id, session_id, False)
