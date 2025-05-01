import gzip
import io

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


def _create_recording_from_session(
    db: Session, org_id: int, session_id: str
) -> Recording:
    """Create a recording from a session"""
    recording = RecordingCreate(
        org_id=org_id,
        session_id=session_id,
        file_name=f"{session_id}/events.json.gzip",
        file_type=VideoType.JSON.value,
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
            s3_service.get_s3_client(), keep_temp_dir=True
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

