from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.issue import Issue
from .schema import IssueCreate, IssueUpdate, IssueResponse, RecordingIntervalInfo, IssueWithIntervalsResponse
from .repository import IssueRepository
from api.v1.org import service as org_service
from common.enums import IntervalCategory
from datetime import datetime


def create_issue(db: Session, org_id: int, issue_data: IssueCreate) -> Issue:
    """Create a new issue"""
    # Verify org exists
    org_service.get_org(db, org_id)

    # Create issue
    repository = IssueRepository(db)
    issue = repository.create(
        Issue(
            title=issue_data.title,
            description=issue_data.description,
            recommendation=issue_data.recommendation,
            severity=issue_data.severity,
            category=issue_data.category.value,
            org_id=org_id,
        )
    )
    return issue


def get_issue(db: Session, issue_id: int, org_id: int, include_intervals: bool = False) -> Issue | IssueWithIntervalsResponse:
    repository = IssueRepository(db)
    issue = repository.get_by_id(issue_id, org_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        )
    
    if not include_intervals:
        return issue
    
    # Get recording intervals for this issue
    intervals_data = repository.get_recording_intervals_for_issue(org_id, issue_id)
    recording_intervals = []
    
    for recording, interval, _ in intervals_data:
        recording_intervals.append(
            RecordingIntervalInfo(
                recording_id=recording.id,
                recording_title=recording.short_title,
                interval_id=interval.id,
                start_time=interval.start_time,
                end_time=interval.end_time,
                description=interval.description,
                category=IntervalCategory(interval.category),
            )
        )
    
    return IssueWithIntervalsResponse(
        **issue.__dict__,
        recording_intervals=recording_intervals
    )


def get_issues(
    db: Session,
    org_id: int,
    skip: int = 0,
    limit: int = 100,
    search: str = None,
    is_resolved: bool = None,
    category: IntervalCategory = None,
    start_date: datetime = None,
    end_date: datetime = None,
) -> list[Issue]:
    repository = IssueRepository(db)
    return repository.get_all(
        org_id, 
        skip, 
        limit, 
        search, 
        is_resolved,
        category.value if category else None,
        start_date,
        end_date,
    )


def get_issues_by_recording(
    db: Session,
    org_id: int,
    recording_id: int,
    skip: int = 0,
    limit: int = 100,
    is_resolved: bool = None,
    category: IntervalCategory = None,
) -> list[Issue]:
    repository = IssueRepository(db)
    return repository.get_issues_by_recording(
        org_id,
        recording_id,
        skip,
        limit,
        is_resolved,
        category.value if category else None,
    )


def update_issue(db: Session, issue_id: int, org_id: int, issue_data: IssueUpdate) -> Issue:
    repository = IssueRepository(db)
    issue = repository.get_by_id(issue_id, org_id)
    if not issue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found"
        )

    # Update only provided fields
    for field, value in issue_data.model_dump(exclude_unset=True).items():
        if field == 'category' and value is not None:
            value = value.value
        setattr(issue, field, value)

    return repository.update(issue)


def soft_delete_issue(db: Session, issue_id: int, org_id: int) -> None:
    repository = IssueRepository(db)
    issue = repository.get_by_id(issue_id, org_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    repository.soft_delete(issue)


def hard_delete_issue(db: Session, issue_id: int, org_id: int) -> None:
    repository = IssueRepository(db)
    issue = repository.get_by_id(issue_id, org_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    repository.delete(issue) 