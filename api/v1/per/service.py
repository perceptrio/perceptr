import asyncio
import gzip
import io
import os
import re
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
from utils.recording import get_file_size
from utils.rrweb import RRWebSessionUtils, merge_rrweb_batches
from graphs.session_analysis import SessionAnalyzer
from common.schemas.session_analysis import SessionAnalysisResult
from api.v1.recording import service as recording_service_module

# Thread pool for CPU-intensive video processing tasks
num_cores = os.cpu_count() or 2
_video_processing_executor = ThreadPoolExecutor(
    max_workers=max(2, num_cores - 1), thread_name_prefix="video_processing"
)

# One stale checker per session at a time; cleared when the checker finishes
_active_stale_checkers: set[str] = set()


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
    force_tier: str = None,
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

            # Load raw rrweb session JSON from merged file
            import json

            with open(merged_file_path, "r", encoding="utf-8") as f:
                raw_session = json.load(f)

            logger.info("Running rrweb SessionAnalyzer graph", session_id=session_id)
            analyzer = SessionAnalyzer()
            analysis_state = analyzer.analyze(raw_session, force_tier=force_tier)
            result: SessionAnalysisResult = analysis_state["result"]
            analysis_tier = analysis_state.get("tier", "tier0")

            # Persist analysis using shared recording service helpers
            rec_repo = recording_service_module.RecordingRepository(db)
            fresh_recording = rec_repo.get_by_id(recording.id, org_id)
            if not fresh_recording:
                raise ValueError(
                    f"Recording {recording.id} not found while saving session analysis"
                )

            # Build intervals
            analyzed_intervals = recording_service_module._build_recording_intervals_from_session_result(  # type: ignore[attr-defined]
                recording.id, result
            )

            # Persist intervals
            from api.v1.recording_intervals import (
                service as recording_intervals_service,
            )

            has_intervals = (
                recording_intervals_service.check_recording_intervals_with_recording_id(
                    db, recording.id
                )
            )
            if has_intervals:
                logger.info(
                    "Replacing existing intervals for recording",
                    recording_id=recording.id,
                )
                recording_intervals_service.replace_recording_intervals(
                    db, recording.id, analyzed_intervals
                )
            else:
                logger.info(
                    "Creating new intervals for recording",
                    recording_id=recording.id,
                )
                recording_intervals_service.batch_create_recording_intervals(
                    db, analyzed_intervals
                )

            # Process issues & tags
            recording_service_module.process_issues_from_session_result(
                db,
                org_id,
                recording.id,
                analyzed_intervals,
                result,
                analysis_tier=analysis_tier,
            )

            # Update recording summary/title directly from SessionAnalysisResult
            fresh_recording.summary = result.summary
            fresh_recording.short_title = result.title
            fresh_recording.set_analysis_status(AnalysisStatus.COMPLETED)
            fresh_recording.analysis_error = None
            fresh_recording.analysis_progress = 100
            fresh_recording.file_duration = session.duration
            fresh_recording.file_size = get_file_size(merged_file_path)
            rec_repo.update(fresh_recording)

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
    org_id: int,
    session_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    force_tier: str = None,
) -> dict:
    """Process a session"""
    try:
        background_tasks.add_task(
            _process_session_background, org_id, session_id, force, force_tier
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
    now = datetime.now(UTC)
    if recording:
        recording.updated_at = now
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


async def check_and_process_stale_recording_async(org_id: int, session_id: str) -> bool:
    """Wait, then run one check. Only process if DB and S3 are both stale (avoids racing SDK uploads).
    Returns True if no reschedule needed (processed or not PENDING); False if still PENDING and not processed (caller may reschedule).
    """
    await asyncio.sleep(settings.STALE_SESSION_DURATION + 5)
    db = SessionLocal()
    try:
        recording = recording_service.get_recording_by_session_id(
            session_id, org_id, db
        )
        if not recording:
            # TODO: maybe add a cleaner to delete stale batches in s3?
            return True

        # Use UTC for comparison
        now = datetime.now(UTC)

        # Ensure recording.updated_at is offset-aware (assuming naive from DB is UTC)
        updated_at_value = recording.updated_at
        if updated_at_value and updated_at_value.tzinfo is None:
            updated_at_value = updated_at_value.replace(tzinfo=UTC)

        time_since_update = (now - updated_at_value).total_seconds()

        # S3: batch count and last upload time (one list call per check)
        session_prefix = f"{org_id}/{session_id}/"
        existing_files = s3_service.list_folder_contents(session_prefix)
        batch_pattern = re.compile(r"batch_(\d+)\.json$")
        batch_files = [
            f for f in existing_files if batch_pattern.search(f.get("key", ""))
        ]
        batch_count = len(batch_files)

        most_recent_batch_time = None
        if batch_files:
            times = [
                f.get("last_modified") for f in batch_files if f.get("last_modified")
            ]
            if times:
                aware = [
                    t.replace(tzinfo=UTC) if t.tzinfo is None else t for t in times
                ]
                most_recent_batch_time = max(aware)

        # Process only if DB and S3 are both stale (no recent URL request and no recent upload)
        is_db_stale = time_since_update > settings.STALE_SESSION_DURATION
        time_since_last_batch = (
            (now - most_recent_batch_time).total_seconds()
            if most_recent_batch_time
            else float("inf")
        )
        is_batch_stale = time_since_last_batch > settings.STALE_SESSION_DURATION
        should_process = (
            recording.analysis_status == AnalysisStatus.PENDING.value
            and is_db_stale
            and batch_count > 0
            and is_batch_stale
        )

        if should_process:
            logger.info(
                "Stale session detected, triggering processing",
                session_id=session_id,
                org_id=org_id,
                batch_count=batch_count,
                time_since_update=time_since_update,
                time_since_last_batch=time_since_last_batch,
            )
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                _process_session_background,
                org_id,
                session_id,
                False,
                None,
            )
            return True  # we processed, no reschedule
        else:
            logger.info(
                "Session not stale or already processed",
                session_id=session_id,
                org_id=org_id,
                status=recording.analysis_status,
                time_since_update=time_since_update,
            )
            # Still PENDING and we didn't process → caller should reschedule so we check again later
            return recording.analysis_status != AnalysisStatus.PENDING.value
    except Exception as e:
        logger.error(
            "Error in stale recording checker",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
        )
        return True  # on error don't reschedule
    finally:
        db.close()


def check_and_process_stale_recording(org_id: int, session_id: str) -> None:
    """Schedule at most one stale checker per session; skip if one is already running."""
    key = f"{org_id}:{session_id}"
    if key in _active_stale_checkers:
        return

    _active_stale_checkers.add(key)

    async def run_then_clear() -> None:
        rescheduled = False
        try:
            no_reschedule = await check_and_process_stale_recording_async(
                org_id, session_id
            )
            if not no_reschedule:
                # Still PENDING and we didn't process (e.g. new batch arrived); run one more check later
                _active_stale_checkers.discard(key)
                check_and_process_stale_recording(org_id, session_id)
                rescheduled = True
        finally:
            if not rescheduled:
                _active_stale_checkers.discard(key)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(run_then_clear())
        else:
            asyncio.run(run_then_clear())
    except RuntimeError:
        asyncio.run(run_then_clear())
