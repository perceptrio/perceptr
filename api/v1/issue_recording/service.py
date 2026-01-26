from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.issue_recording import IssueRecording
from .repository import IssueRecordingRepository
from api.v1.org import service as org_service
from api.v1.recording import service as recording_service
from api.v1.issue import service as issue_service


def create_issue_recording(
    db: Session,
    org_id: int,
    issue_id: int,
    recording_id: int,
    recording_interval_id: int,
) -> IssueRecording:
    """Create a relationship between an issue and a recording interval"""
    # Verify org exists
    org_service.get_org(db, org_id)

    # Verify issue exists and belongs to org
    issue_service.get_issue(db, issue_id, org_id)

    # Verify recording exists and belongs to org
    recording_service.get_recording(db, recording_id, org_id)

    # Create relationship
    repository = IssueRecordingRepository(db)

    # Check if relationship already exists
    existing = repository.get_by_issue_and_interval(org_id, issue_id, recording_interval_id)
    if existing:
        if existing.deleted_at:
            # If soft deleted, reactivate it
            existing.deleted_at = None
            return repository.update(existing)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Relationship already exists between this issue and recording interval",
        )

    issue_recording = repository.create(
        IssueRecording(
            org_id=org_id,
            issue_id=issue_id,
            recording_id=recording_id,
            recording_interval_id=recording_interval_id,
        )
    )
    return issue_recording


def get_issue_recording(
    db: Session, id: int, org_id: int
) -> IssueRecording:
    """Get a specific issue-recording relationship"""
    repository = IssueRecordingRepository(db)
    issue_recording = repository.get_by_id(id, org_id)
    if not issue_recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue-Recording relationship not found",
        )
    return issue_recording


def get_by_recording_interval(
    db: Session, org_id: int, recording_interval_id: int
) -> list[IssueRecording]:
    """Get all issues linked to a recording interval"""
    repository = IssueRecordingRepository(db)
    return repository.get_by_recording_interval(org_id, recording_interval_id)


def get_by_recording(
    db: Session, org_id: int, recording_id: int
) -> list[IssueRecording]:
    """Get all issues linked to a recording"""
    repository = IssueRecordingRepository(db)
    return repository.get_by_recording(org_id, recording_id)


def get_by_issue(
    db: Session, org_id: int, issue_id: int
) -> list[IssueRecording]:
    """Get all recordings linked to an issue"""
    repository = IssueRecordingRepository(db)
    return repository.get_by_issue(org_id, issue_id)


def soft_delete_issue_recording(
    db: Session, id: int, org_id: int
) -> None:
    """Soft delete a relationship between an issue and a recording interval"""
    repository = IssueRecordingRepository(db)
    issue_recording = repository.get_by_id(id, org_id)
    if not issue_recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue-Recording relationship not found",
        )
    repository.soft_delete(issue_recording)


def hard_delete_issue_recording(
    db: Session, id: int, org_id: int
) -> None:
    """Hard delete a relationship between an issue and a recording interval"""
    repository = IssueRecordingRepository(db)
    issue_recording = repository.get_by_id(id, org_id)
    if not issue_recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Issue-Recording relationship not found",
        )
    repository.delete(issue_recording)