import asyncio
import gzip
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from api.v1.recording import service as recording_service
from api.v1.recording.schema import RecordingCreate
from common.enums import AnalysisStatus, VideoType
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from core.constants import SDK_FILE_EXTENSION
from database import SessionLocal
from fastapi import BackgroundTasks
from models.recording import Recording
from settings import settings
from sqlalchemy.orm import Session
from utils.rrweb import RRWebSessionUtils, merge_rrweb_batches

# Thread pool for CPU-intensive video processing tasks
_video_processing_executor = ThreadPoolExecutor(
    max_workers=2, thread_name_prefix="video_processing"
)


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
    org_id: int,
    session_id: str,
    force: bool = False,
) -> None:
    """Background task to process a session - creates its own DB session"""
    db = SessionLocal()
    try:
        recording = recording_service.get_recording_by_session_id(
            session_id, org_id, db
        )
        if not recording:
            logger.error(
                "Recording not found while processing session",
                session_id=session_id,
                org_id=org_id,
            )
            return

        # Check status with proper locking by refreshing from DB
        db.refresh(recording)
        if recording.analysis_status != AnalysisStatus.PENDING.value and not force:
            logger.info(
                "Skipping analysis for non-pending session",
                session_id=session_id,
                org_id=org_id,
                current_status=recording.analysis_status,
            )
            return

        # Update status to IN_PROGRESS to prevent race conditions
        recording.set_analysis_status(AnalysisStatus.IN_PROGRESS)
        recording_service.update_recording(db, recording)
    except Exception as e:
        logger.error(
            "Error checking recording status",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
        )
        db.close()
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

            # Check if any files were downloaded
            if not local_file_paths:
                raise ValueError(
                    f"No batch files found in S3 for session {session_id} with prefix {session_prefix}"
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
                # Update status to COMPLETED since there's nothing to analyze
                recording = recording_service.get_recording(db, recording.id, org_id)
                recording.set_analysis_status(AnalysisStatus.COMPLETED)
                recording.analysis_error = None
                recording_service.update_recording(db, recording)
                return

            # Convert to video - run in thread pool to avoid blocking
            logger.info("Starting video conversion", session_id=session_id)
            # Run rrvideo conversion in thread pool to avoid blocking
            future = _video_processing_executor.submit(session.convert_events_to_video)
            result = future.result()  # Wait for result but doesn't block main thread

            if result["success"]:
                logger.info(
                    "Video conversion successful",
                    session_id=session_id,
                    output_path=result["output_path"],
                )
                if settings.AI_ANALYSIS_ENABLED:
                    # Run analysis in thread pool to avoid blocking
                    future = _video_processing_executor.submit(
                        recording_service.analyze_local_recording_video,
                        db,
                        org_id,
                        recording.id,
                        recording,
                        result["output_path"],
                    )
                    future.result()  # Wait for completion
                else:
                    # Update status to COMPLETED if analysis is disabled
                    recording = recording_service.get_recording(
                        db, recording.id, org_id
                    )
                    recording.set_analysis_status(AnalysisStatus.COMPLETED)
                    recording.analysis_error = None
                    recording_service.update_recording(db, recording)
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
        error_type = type(e).__name__
        logger.error(
            "Error processing session background",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
            recording_id=recording.id if recording else None,
            error_type=error_type,
            error_message=str(e),
        )
        try:
            # Ensure we have a fresh recording instance for error handling
            recording = (
                recording_service.get_recording(db, recording.id, org_id)
                if recording
                else None
            )
            if recording:
                recording.set_analysis_status(AnalysisStatus.FAILED)
                recording.analysis_error = str(e)
                recording_service.update_recording(db, recording)
        except Exception as update_err:
            logger.error(
                "Failed to update recording status to FAILED",
                exc_info=update_err,
                session_id=session_id,
                org_id=org_id,
            )
    finally:
        db.close()


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
            _process_session_background, org_id, session_id, force
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


async def check_and_process_stale_recording_async(org_id: int, session_id: str):
    """Async version of stale recording checker - uses asyncio.sleep instead of blocking time.sleep"""
    # Use async sleep to avoid blocking the event loop
    await asyncio.sleep(settings.STALE_SESSION_DURATION + 5)

    db = SessionLocal()
    try:
        recording = recording_service.get_recording_by_session_id(
            session_id, org_id, db
        )
        if not recording:
            # TODO: maybe add a cleaner to delete stale batches in s3?
            return

        # Use UTC for comparison
        now = datetime.now(UTC)

        # Ensure recording.updated_at is offset-aware (assuming naive from DB is UTC)
        updated_at_value = recording.updated_at
        if updated_at_value and updated_at_value.tzinfo is None:
            updated_at_value = updated_at_value.replace(tzinfo=UTC)

        if recording.analysis_status == AnalysisStatus.PENDING.value and (
            now - updated_at_value
        ) > timedelta(seconds=settings.STALE_SESSION_DURATION):
            # Trigger processing - run sync function in thread pool
            logger.info(
                "Stale session detected, triggering processing",
                session_id=session_id,
                org_id=org_id,
                updated_at=updated_at_value,
                now=now,
            )
            # Run sync function in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                _process_session_background,
                org_id,
                session_id,
                False,
            )
        else:
            logger.info(
                "Session is not stale or already processed",
                session_id=session_id,
                org_id=org_id,
                status=recording.analysis_status,
                time_since_update=(now - updated_at_value).total_seconds(),
            )
    except Exception as e:
        logger.error(
            "Error in stale recording checker",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
        )
    finally:
        db.close()


def check_and_process_stale_recording(org_id: int, session_id: str):
    """Wrapper to run async stale checker - creates task in event loop"""
    # Create a task in the event loop
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, create a task
            asyncio.create_task(
                check_and_process_stale_recording_async(org_id, session_id)
            )
        else:
            # If no loop is running, run it
            asyncio.run(check_and_process_stale_recording_async(org_id, session_id))
    except RuntimeError:
        # If no event loop exists, create one
        asyncio.run(check_and_process_stale_recording_async(org_id, session_id))
