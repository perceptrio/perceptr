from datetime import datetime
from sqlalchemy.orm import Session
from models.issue_recording import IssueRecording
from models.issue import Issue
from models.recording import Recording
from models.recording_interval import RecordingInterval
from sqlalchemy import and_


class IssueRecordingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, issue_recording: IssueRecording) -> IssueRecording:
        self.db.add(issue_recording)
        self.db.commit()
        self.db.refresh(issue_recording)
        return issue_recording

    def get_by_id(self, id: int, org_id: int) -> IssueRecording | None:
        return (
            self.db.query(IssueRecording)
            .filter(IssueRecording.id == id, IssueRecording.org_id == org_id)
            .first()
        )

    def update(self, issue_recording: IssueRecording) -> IssueRecording:
        """Update an issue recording relationship"""
        self.db.commit()
        self.db.refresh(issue_recording)
        return issue_recording

    def get_by_issue_and_interval(
        self, org_id: int, issue_id: int, recording_interval_id: int
    ) -> IssueRecording | None:
        """Get the relationship between an issue and a recording interval"""
        return (
            self.db.query(IssueRecording)
            .filter(
                and_(
                    IssueRecording.org_id == org_id,
                    IssueRecording.issue_id == issue_id,
                    IssueRecording.recording_interval_id == recording_interval_id,
                    IssueRecording.deleted_at == None,
                )
            )
            .first()
        )

    def get_by_recording_interval(
        self, org_id: int, recording_interval_id: int
    ) -> list[IssueRecording]:
        """Get all issue relationships for a recording interval"""
        return (
            self.db.query(IssueRecording)
            .filter(
                and_(
                    IssueRecording.org_id == org_id,
                    IssueRecording.recording_interval_id == recording_interval_id,
                    IssueRecording.deleted_at == None,
                )
            )
            .all()
        )

    def get_by_recording(
        self, org_id: int, recording_id: int
    ) -> list[IssueRecording]:
        """Get all issue relationships for a recording"""
        return (
            self.db.query(IssueRecording)
            .filter(
                and_(
                    IssueRecording.org_id == org_id,
                    IssueRecording.recording_id == recording_id,
                    IssueRecording.deleted_at == None,
                )
            )
            .all()
        )

    def get_by_issue(
        self, org_id: int, issue_id: int
    ) -> list[IssueRecording]:
        """Get all recording relationships for an issue"""
        return (
            self.db.query(IssueRecording)
            .filter(
                and_(
                    IssueRecording.org_id == org_id,
                    IssueRecording.issue_id == issue_id,
                    IssueRecording.deleted_at == None,
                )
            )
            .all()
        )

    def soft_delete(self, issue_recording: IssueRecording) -> IssueRecording:
        """Soft delete a relationship between an issue and a recording interval"""
        issue_recording.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(issue_recording)
        return issue_recording

    def delete(self, issue_recording: IssueRecording) -> None:
        """Hard delete a relationship between an issue and a recording interval"""
        self.db.delete(issue_recording)
        self.db.commit() 