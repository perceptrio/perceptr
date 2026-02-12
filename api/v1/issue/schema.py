from datetime import datetime, time
from typing import Optional

from common.enums import IntervalCategory
from pydantic import BaseModel


class IssueBase(BaseModel):
    title: str
    description: Optional[str] = None
    root_cause: Optional[str] = None
    recommendation: Optional[str] = None
    severity: str
    category: IntervalCategory = IntervalCategory.NORMAL
    type: Optional[str] = None
    target: Optional[str] = None
    confidence: Optional[str] = None


class IssueCreate(IssueBase):
    pass


class IssueUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    root_cause: Optional[str] = None
    recommendation: Optional[str] = None
    severity: Optional[str] = None
    category: Optional[IntervalCategory] = None
    type: Optional[str] = None
    target: Optional[str] = None
    confidence: Optional[str] = None
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
    root_cause: str | None
    recommendation: str | None
    severity: str
    category: IntervalCategory
    type: str | None
    target: str | None
    confidence: str | None
    is_resolved: bool
    created_at: datetime
    updated_at: datetime
    recording_count: int = 0

    class Config:
        from_attributes = True


class IssueWithRecordingResponse(BaseModel):
    title: str
    is_resolved: bool
    type: str | None
    target: str | None
    confidence: str | None
    timestamp: str | None
    frequency: int | None
    severity: str
    category: str
    root_cause: str | None
    reproduction_steps: str | None
    analysis_tier: str | None
    updated_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class IssueWithIntervalsResponse(IssueResponse):
    recording_intervals: list[RecordingIntervalInfo] = []

    class Config:
        from_attributes = True
