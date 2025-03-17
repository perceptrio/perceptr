from sqlalchemy.orm import Session
from api.v1.recording.schema import RecordingCreate
from models.org import Org
from models.recording import Recording
from .schema import SnapshotBuffer
from common.services.s3 import s3_service
from common.services.logger import logger
import json
import gzip
import io
from fastapi import BackgroundTasks
from api.v1.recording import service as recording_service
from common.enums import AnalysisStatus
from api.v1.org import service as org_service
from api.v1.recording import service as recording_service


def get_org_by_project_id(db: Session, project_id: str) -> Org:
    """Get organization by project ID"""
    return org_service.get_org_by_project_id(db, project_id)


def _compress_jsonl(content: str) -> bytes:
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
            file_type="application/gzip",
            file_size=0,
            client_id=client_id,
            client_data=user_metadata,
            meta_data=snapshot_buffer.metadata or {},
            analysis_status=AnalysisStatus.PENDING.value,
        )
        recording = recording_service.create_recording(db, recording)
        logger.info(f"Created new recording for session: {snapshot_buffer.sessionId}")
        return recording, True

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
        compressed_bytes = _compress_jsonl(updated_content.decode("utf-8"))
    else:
        # Create new file
        compressed_bytes = _compress_jsonl(json_line)

    # Upload to S3
    s3_service.upload_file(s3_path, compressed_bytes)
    # Update file size
    recording.file_size = len(compressed_bytes)
    recording_service.update_recording(db, recording)


def process_events(
    db: Session,
    org_id: int,
    snapshot_buffer: SnapshotBuffer,
    background_tasks: BackgroundTasks,
) -> dict:
    """Process incoming event buffer from the SDK"""

    # 1. Get or create recording
    recording, _ = _get_or_create_recording(db, org_id, snapshot_buffer)
    if recording.analysis_status != AnalysisStatus.PENDING.value:
        return {"success": True, "message": "Recording is not pending"}

    # 2. Upload events to S3
    s3_path = f"{org_id}/{snapshot_buffer.sessionId}/events.jsonl.gz"
    json_line = json.dumps(snapshot_buffer.model_dump()) + "\n"
    _update_recording_file(db, recording, s3_path, json_line)

    # 3. Update recording status if session ended
    if snapshot_buffer.isSessionEnded:
        recording.analysis_status = AnalysisStatus.IN_PROGRESS.value
        recording = recording_service.update_recording(db, recording)
        logger.info(f"Session ended, analysis in progress: {snapshot_buffer.sessionId}")
        # Schedule analysis
        background_tasks.add_task(
            schedule_session_analysis, db, org_id, snapshot_buffer.sessionId
        )

    return {"success": True, "message": "Events processed successfully"}


def schedule_session_analysis(db: Session, org_id: int, session_id: str):
    """Background task to trigger session analysis"""
    logger.info(f"TODO: Implement session analysis for {session_id}")
    # This would be implemented to call your analysis pipeline
    # For example:
    # recording_service.analyze_recording(db, org_id, session_id, recording)
