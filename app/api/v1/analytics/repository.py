from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from models.recording import Recording
from models.issue import Issue
from models.issue_recording import IssueRecording
from common.enums import AnalysisStatus


class AnalyticsRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_key_metrics(self, org_id: int) -> dict:
        # Get number of analyzed sessions
        sessions_analyzed = (
            self.db.query(func.count(Recording.id))
            .filter(
                Recording.org_id == org_id,
                Recording.analysis_status == AnalysisStatus.COMPLETED.value,
                Recording.deleted_at == None,
            )
            .scalar()
        )

        # Get total number of issues
        issues_found = (
            self.db.query(func.count(Issue.id))
            .filter(Issue.org_id == org_id, Issue.deleted_at == None)
            .scalar()
        )

        # Get number of resolved issues
        issues_resolved = (
            self.db.query(func.count(Issue.id))
            .filter(
                Issue.org_id == org_id,
                Issue.is_resolved == True,
                Issue.deleted_at == None,
            )
            .scalar()
        )

        # Get number of normal sessions (no issues)
        recordings_with_issues = (
            self.db.query(IssueRecording.recording_id)
            .join(Recording, Recording.id == IssueRecording.recording_id)
            .filter(
                Recording.org_id == org_id,
                Recording.analysis_status == AnalysisStatus.COMPLETED.value,
                Recording.deleted_at == None,
                IssueRecording.deleted_at == None,
            )
            .distinct()
            .subquery()
        )

        normal_sessions = (
            self.db.query(func.count(Recording.id))
            .filter(
                Recording.org_id == org_id,
                Recording.analysis_status == AnalysisStatus.COMPLETED.value,
                Recording.deleted_at == None,
                ~Recording.id.in_(recordings_with_issues),
            )
            .scalar()
        )

        return {
            "sessions_analyzed": sessions_analyzed or 0,
            "issues_found": issues_found or 0,
            "issues_resolved": issues_resolved or 0,
            "normal_sessions": normal_sessions or 0,
        }
