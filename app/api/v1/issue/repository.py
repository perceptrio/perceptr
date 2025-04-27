from datetime import datetime

from common.enums import IntervalCategory, IntervalSeverity, IssueSortBy
from models.issue import Issue
from models.issue_recording import IssueRecording
from models.recording import Recording
from models.recording_interval import RecordingInterval
from sqlalchemy import and_, func
from sqlalchemy.orm import Session


class IssueRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, issue: Issue) -> Issue:
        self.db.add(issue)
        self.db.commit()
        self.db.refresh(issue)
        return issue

    def get_by_id(self, issue_id: int, org_id: int) -> Issue | None:
        return (
            self.db.query(Issue)
            .filter(Issue.id == issue_id, Issue.org_id == org_id)
            .first()
        )

    def get_all(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 100,
        sort_by: IssueSortBy = IssueSortBy.LATEST,
        search: str = None,
        is_resolved: bool = None,
        categories: list[IntervalCategory] = None,
        severities: list[IntervalSeverity] = None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> list[Issue]:
        query = (
            self.db.query(
                Issue, func.count(IssueRecording.recording_id).label("recording_count")
            )
            .outerjoin(IssueRecording, Issue.id == IssueRecording.issue_id)
            .filter(
                Issue.org_id == org_id,
                Issue.deleted_at == None,
            )
            .group_by(Issue.id)
        )

        if is_resolved is not None:
            query = query.filter(Issue.is_resolved == is_resolved)

        if search:
            search = f"%{search}%"
            query = query.filter(
                Issue.title.ilike(search) | Issue.description.ilike(search)
            )

        if categories is not None:
            query = query.filter(
                Issue.category.in_([category.value for category in categories])
            )

        if severities is not None:
            query = query.filter(
                Issue.severity.in_([severity.value for severity in severities])
            )

        if start_date:
            query = query.filter(Issue.created_at >= start_date)

        if end_date:
            query = query.filter(Issue.created_at <= end_date)

        if sort_by.value == IssueSortBy.LATEST.value:
            query = query.order_by(Issue.created_at.desc())
        elif sort_by.value == IssueSortBy.OLDEST.value:
            query = query.order_by(Issue.created_at.asc())
        elif sort_by.value == IssueSortBy.MOST_AFFECTED.value:
            query = query.order_by(func.count(IssueRecording.recording_id).desc())
        elif sort_by.value == IssueSortBy.LEAST_AFFECTED.value:
            query = query.order_by(func.count(IssueRecording.recording_id).asc())

        return query.offset(skip).limit(limit).all()

    def get_issues_by_recording(
        self,
        org_id: int,
        recording_id: int,
        skip: int = 0,
        limit: int = 100,
        is_resolved: bool = None,
        category: str = None,
    ) -> list[Issue]:
        """Get all issues that appear in a specific recording"""
        query = (
            self.db.query(Issue)
            .join(IssueRecording)
            .filter(
                and_(
                    Issue.org_id == org_id,
                    Issue.deleted_at == None,
                    IssueRecording.recording_id == recording_id,
                    IssueRecording.deleted_at == None,
                )
            )
        )

        if is_resolved is not None:
            query = query.filter(Issue.is_resolved == is_resolved)

        if category:
            query = query.filter(Issue.category == category)

        return query.offset(skip).limit(limit).all()

    def get_recording_intervals_for_issue(
        self,
        org_id: int,
        issue_id: int,
    ) -> list[dict]:
        """Get all recording intervals where this issue appears"""
        return (
            self.db.query(
                Recording,
                RecordingInterval,
                IssueRecording,
            )
            .join(IssueRecording, IssueRecording.recording_id == Recording.id)
            .join(
                RecordingInterval,
                RecordingInterval.id == IssueRecording.recording_interval_id,
            )
            .filter(
                and_(
                    Recording.org_id == org_id,
                    IssueRecording.issue_id == issue_id,
                    Recording.deleted_at == None,
                    RecordingInterval.deleted_at == None,
                    IssueRecording.deleted_at == None,
                )
            )
            .all()
        )

    def update(self, issue: Issue) -> Issue:
        self.db.commit()
        self.db.refresh(issue)
        return issue

    def soft_delete(self, issue: Issue) -> Issue:
        issue.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(issue)
        return issue

    def delete(self, issue: Issue) -> None:
        self.db.delete(issue)
        self.db.commit()
