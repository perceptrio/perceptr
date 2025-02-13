from fastapi import APIRouter, Depends, status
from core.constants import APIPath
from .schema import IssueCreate, IssueUpdate, IssueResponse, IssueWithIntervalsResponse
from . import service
from common.types import TokenPayload
from typing_extensions import Annotated
from common.middleware import GetPayload
from sqlalchemy.orm import Session
from database import get_db
from typing import List
from common.enums import IntervalCategory
from datetime import datetime

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
    search: str = None,
    is_resolved: bool = None,
    category: IntervalCategory = None,
    start_date: datetime = None,
    end_date: datetime = None,
):
    issues = service.get_issues(
        db,
        payload.org.id,
        skip,
        limit,
        search,
        is_resolved,
        category,
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
