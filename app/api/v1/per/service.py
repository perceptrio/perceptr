import gzip
import io
import json

from api.v1.org import service as org_service
from api.v1.recording import service as recording_service
from api.v1.recording.schema import RecordingCreate
from common.enums import AnalysisStatus, VideoType
from common.services.files_downloader import FilesDownloader
from common.services.logger import logger
from common.services.s3 import s3_service
from fastapi import BackgroundTasks
from models.org import Org
from models.recording import Recording
from settings import settings
from sqlalchemy.orm import Session
from utils.rrweb import RRWebSessionUtils, merge_rrweb_batches

from .schema import SnapshotBuffer


def get_org_by_project_id(db: Session, project_id: str) -> Org:
    """Get organization by project ID"""
    return org_service.get_org_by_project_id(db, project_id)


def get_recording_by_session_id(db: Session, org_id: int, session_id: str) -> Recording:
    """Get recording by session ID"""
    return recording_service.get_recording_by_session_id(
        session_id=session_id, org_id=org_id, db=db
    )


def _compress_content(content: str) -> bytes:
    """Compress content using gzip"""
    compressed_content = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed_content, mode="wb") as f:
        f.write(content.encode("utf-8"))
    return compressed_content.getvalue()


def _decompress_gzip(content: bytes) -> bytes:
    """Decompress gzipped content"""
    with gzip.GzipFile(fileobj=io.BytesIO(content), mode="rb") as f:
        return f.read()


def _get_or_create_recording(
    db: Session, org_id: int, snapshot_buffer: SnapshotBuffer
) -> tuple[Recording, bool]:
    """Get or create a recording for the session

    Returns:
        tuple: (recording, is_new)
    """
    logger.info(
        "Getting or creating recording for session",
        session_id=snapshot_buffer.sessionId,
        org_id=org_id,
    )
    recording = recording_service.get_recording_by_session_id(
        snapshot_buffer.sessionId, org_id, db
    )

    # Process user identity
    user_metadata = None
    client_id = None
    if snapshot_buffer.userIdentity:
        client_id = snapshot_buffer.userIdentity.distinctId
        user_metadata = snapshot_buffer.userIdentity.model_dump()

    if not recording:
        # Generate a file name based on session ID
        file_name = f"{snapshot_buffer.sessionId}/events.jsonl.gz"

        recording = RecordingCreate(
            org_id=org_id,
            session_id=snapshot_buffer.sessionId,
            file_name=file_name,
            file_type=VideoType.GZIP.value,
            file_size=0,
            client_id=client_id,
            client_data=user_metadata,
            meta_data=snapshot_buffer.metadata or {},
            analysis_status=AnalysisStatus.PENDING.value,
        )
        try:
            recording = recording_service.create_recording(db, recording)
            logger.info(
                "Created new recording for session",
                session_id=snapshot_buffer.sessionId,
                org_id=org_id,
            )
            return recording, True
        except Exception as e:
            # If a unique constraint violation occurred,
            #  try to fetch the recording again
            if (
                "unique constraint" in str(e).lower()
                or "duplicate key" in str(e).lower()
            ):
                logger.info(
                    "Race condition detected for session",
                    session_id=snapshot_buffer.sessionId,
                    org_id=org_id,
                )
                db.rollback()  # Roll back the failed transaction
                recording = recording_service.get_recording_by_session_id(
                    snapshot_buffer.sessionId, org_id, db
                )
                if recording:
                    return recording, False
            raise

    # Update user data if needed
    if client_id and (
        recording.client_id != client_id or recording.client_data != user_metadata
    ):
        recording.client_id = client_id
        recording.client_data = user_metadata
        recording = recording_service.update_recording(db, recording)

    return recording, False


def _update_recording_file(
    db: Session, recording: Recording, s3_path: str, json_line: str
) -> None:
    """Update the recording's file in S3"""
    file_exists = s3_service.check_file_exists(s3_path)
    compressed_bytes = None
    if file_exists:
        # Get existing content
        content = s3_service.download_file(s3_path)
        # Decompress, append, and recompress
        existing_content = _decompress_gzip(content)
        updated_content = existing_content + json_line.encode("utf-8")
        compressed_bytes = _compress_content(updated_content.decode("utf-8"))
    else:
        # Create new file
        compressed_bytes = _compress_content(json_line)

    # Upload to S3
    s3_service.upload_file(s3_path, compressed_bytes)
    # Update file size
    recording.file_size = len(compressed_bytes)
    recording_service.update_recording(db, recording)


def _process_events_background(
    db: Session,
    org_id: int,
    recording_id: int,
    snapshot_buffer: SnapshotBuffer,
    background_tasks: BackgroundTasks,
) -> None:
    """Background task to process events and upload to S3"""
    try:
        # Get a fresh recording instance in this session
        recording = recording_service.get_recording(db, recording_id, org_id)
        if not recording:
            logger.error(
                "Recording not found in background task",
                recording_id=recording_id,
                org_id=org_id,
            )
            return

        # Process events and upload to S3
        json_line = snapshot_buffer.model_dump_json()
        s3_path = f"{org_id}/{snapshot_buffer.sessionId}/events.jsonl.gz"
        _update_recording_file(db, recording, s3_path, json_line)

        logger.info(
            "Events processed successfully",
            session_id=snapshot_buffer.sessionId,
            org_id=org_id,
            recording_id=recording_id,
        )

        # Schedule analysis as a nested background task
        background_tasks.add_task(
            schedule_session_analysis,
            db,
            org_id,
            recording_id,
            snapshot_buffer.sessionId,
        )
    except Exception as e:
        logger.error(
            "Error processing events in background",
            exc_info=e,
            session_id=snapshot_buffer.sessionId,
            org_id=org_id,
            recording_id=recording_id,
        )
        try:
            # Get a fresh recording instance for error handling
            recording = recording_service.get_recording(db, recording_id, org_id)
            if recording:
                recording.analysis_status = AnalysisStatus.FAILED.value
                recording.analysis_error = str(e)
                recording_service.update_recording(db, recording)
        except Exception as inner_e:
            logger.error(
                "Error updating recording status",
                exc_info=inner_e,
                session_id=snapshot_buffer.sessionId,
                org_id=org_id,
                recording_id=recording_id,
                original_error=str(e),
            )


def _create_recording_from_session(
    db: Session, org_id: int, session_id: str
) -> Recording:
    """Create a recording from a session"""
    recording = RecordingCreate(
        org_id=org_id,
        session_id=session_id,
        file_name=f"{session_id}/events.json.gzip",
        file_type=VideoType.WEBM.value,
        file_size=0,
        analysis_status=AnalysisStatus.IN_PROGRESS.value,
    )
    return recording_service.create_recording(db, recording)


def _process_session_background(
    db: Session,
    org_id: int,
    session_id: str,
    recording: Recording,
) -> None:
    """Background task to process a session"""

    try:
        logger.info(
            "Processing session started",
            session_id=session_id,
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
            s3_path = f"{org_id}/{session_id}/events.json.gzip"
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
) -> dict:
    """Process a session"""
    try:
        recording = _create_recording_from_session(db, org_id, session_id)
        if not recording:
            raise ValueError("Failed to create recording")

        background_tasks.add_task(
            _process_session_background,
            db,
            org_id,
            session_id,
            recording,
        )

        return {"success": True, "message": "Session scheduled for processing"}
    except Exception as e:
        logger.error(
            "Error processing session",
            exc_info=e,
            session_id=session_id,
            org_id=org_id,
            recording_id=recording.id,
        )
        raise


def process_events(
    db: Session,
    org_id: int,
    snapshot_buffer: SnapshotBuffer,
    background_tasks: BackgroundTasks,
) -> dict:
    """Process incoming event buffer from the SDK"""

    # 1. Get or create recording - this needs to be done synchronously
    recording, _ = _get_or_create_recording(db, org_id, snapshot_buffer)
    if recording.analysis_status != AnalysisStatus.PENDING.value:
        return {"success": True, "message": "Recording is not pending"}

    # 2. Schedule the rest of the processing in background
    background_tasks.add_task(
        _process_events_background,
        db,
        org_id,
        recording.id,
        snapshot_buffer,
        background_tasks,
    )

    return {"success": True, "message": "Events scheduled for processing"}


def _decompress_and_save_json(content: bytes, output_path: str) -> str:
    """Decompress gzipped content and save to a JSON file

    Args:
        content: Compressed gzip content
        output_path: Path to save the JSON file

    Returns:
        Path to the saved JSON file
    """
    # Decompress content
    decompressed_content = _decompress_gzip(content)

    # Save raw decompressed content to file
    with open(output_path, "wb") as f:
        f.write(decompressed_content)

    return output_path


def schedule_session_analysis(
    db: Session, org_id: int, recording_id: int, session_id: str
) -> None:
    """Background task to trigger session analysis"""
    logger.info(f"TODO: Implement session analysis", session_id=session_id)
    recording = recording_service.get_recording(db, recording_id, org_id)
    s3_path = f"{org_id}/{session_id}/events.jsonl.gz"
    with FilesDownloader(s3_service.get_s3_client(), keep_temp_dir=False) as downloader:
        local_file_path = downloader.download_file_from_s3(s3_path)

        # Read the compressed file
        with open(local_file_path, "rb") as file:
            compressed_content = file.read()

        # Decompress and save as JSON
        json_path = local_file_path.replace(".jsonl.gz", ".json")
        _decompress_and_save_json(compressed_content, json_path)

        logger.info(
            "Saved JSON events",
            session_id=session_id,
            json_path=json_path,
        )

        session = RRWebSessionUtils(json_path)

        # Print session summary
        duration = session.get_duration()
        logger.info(
            "Session summary",
            session_id=session_id,
            summary=session.get_session_summary(),
            start_time=session.get_start_time(),
            end_time=session.get_end_time(),
            duration=duration,
            event_count=len(session.get_events()),
            user_identity=session.get_user_identity(),
        )
        # Skip sessions with 0 duration
        if duration == "00:00:00":
            logger.info(
                "Skipping analysis for session with 0 duration",
                session_id=session_id,
            )
            return

        # Convert to video
        logger.info("Converting session to video...")
        result = session.convert_events_to_video()

        if result["success"]:
            logger.info(
                "Video saved",
                session_id=session_id,
                output_path=result["output_path"],
            )
            if settings.AI_ANALYSIS_ENABLED:
                recording_service.analyze_local_recording_video(
                    db, org_id, recording_id, recording, result["output_path"]
                )
            else:
                logger.info("AI analysis is disabled, skipping analysis")
        else:
            logger.error("Video conversion failed!", session_id=session_id)
            if "error" in result:
                logger.error(
                    "Video conversion failed",
                    session_id=session_id,
                    error=result["error"],
                )
            else:
                logger.error(
                    "Video conversion failed",
                    session_id=session_id,
                    message=result["message"],
                )
