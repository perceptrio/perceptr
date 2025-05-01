from datetime import datetime
from typing import List

from common.enums import IntervalCategory, IntervalSeverity, IssueSortBy
from common.middleware.auth_token import GetPayload
from common.types import TokenPayload
from core.constants import APIPath
from database import get_db
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from typing_extensions import Annotated
from utils import get_issues_categories, get_issues_severities, get_issues_sort_by

from . import service
from .schema import IssueCreate, IssueResponse, IssueUpdate, IssueWithIntervalsResponse

router = APIRouter(prefix=f"{APIPath.V1}/issues", tags=["issues"])


@router.post("/", response_model=IssueResponse)
def create_issue(
    issue: IssueCreate,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    issue = service.create_issue(db, payload.org.id, issue)
    return issue


@router.get("/{issue_id}", response_model=IssueWithIntervalsResponse)
def get_issue(
    issue_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
    include_intervals: bool = True,
):
    issue = service.get_issue(db, issue_id, payload.org.id, include_intervals)
    return issue


@router.get("/", response_model=List[IssueResponse])
def get_issues_for_org(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    sort_by: IssueSortBy = Depends(get_issues_sort_by),
    search: str = None,
    is_resolved: bool = None,
    categories: list[IntervalCategory] | None = Depends(get_issues_categories),
    severities: list[IntervalSeverity] | None = Depends(get_issues_severities),
    start_date: datetime = None,
    end_date: datetime = None,
):
    issues = service.get_issues(
        db,
        payload.org.id,
        skip,
        limit,
        sort_by,
        search,
        is_resolved,
        categories,
        severities,
        start_date,
        end_date,
    )
    return issues


@router.get("/by-recording/{recording_id}", response_model=List[IssueResponse])
def get_issues_by_recording(
    recording_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    is_resolved: bool = None,
    category: IntervalCategory = None,
):
    issues = service.get_issues_by_recording(
        db,
        payload.org.id,
        recording_id,
        skip,
        limit,
        is_resolved,
        category,
    )
    return issues


@router.patch("/{issue_id}", response_model=IssueResponse)
def update_issue(
    issue_id: int,
    issue: IssueUpdate,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    updated_issue = service.update_issue(db, issue_id, payload.org.id, issue)
    return updated_issue


@router.delete("/{issue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_issue(
    issue_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    service.soft_delete_issue(db, issue_id, payload.org.id)
    return


@router.delete("/{issue_id}/hard", status_code=status.HTTP_204_NO_CONTENT)
def hard_delete_issue(
    issue_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    service.hard_delete_issue(db, issue_id, payload.org.id)
    return
