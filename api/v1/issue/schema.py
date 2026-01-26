from datetime import datetime, time
from typing import Optional

from common.enums import IntervalCategory
from pydantic import BaseModel


class IssueBase(BaseModel):
    title: str
    description: Optional[str] = None
    recommendation: Optional[str] = None
    severity: str
    category: IntervalCategory = IntervalCategory.NORMAL


class IssueCreate(IssueBase):
    pass


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    recommendation: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[IntervalCategory] = None
    is_resolved: Optional[bool] = None


class RecordingIntervalInfo(BaseModel):
    recording_id: int
    recording_session_id: str | None
    recording_file_size: int
    recording_duration: float
    recording_created_at: datetime
    recording_title: str | None
    recording_summary: str | None
    interval_id: int
    start_time: time
    end_time: time
    description: str
    category: IntervalCategory

    class Config:
        from_attributes = True


class IssueResponse(IssueBase):
    id: int
    org_id: int
    title: str
    description: str | None
    recommendation: str | None
    severity: str
    category: IntervalCategory
    is_resolved: bool
    created_at: datetime
    updated_at: datetime
    recording_count: int = 0

    class Config:
        from_attributes = True


class IssueWithIntervalsResponse(IssueResponse):
    recording_intervals: list[RecordingIntervalInfo] = []

    class Config:
        from_attributes = True
