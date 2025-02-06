from datetime import datetime, time
from pydantic import BaseModel
from common.enums import IntervalCategory


class IssueCreate(BaseModel):
    title: str
    description: str | None = None
    recommendation: str | None = None
    severity: str
    category: IntervalCategory = IntervalCategory.NORMAL


class IssueUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    recommendation: str | None = None
    severity: str | None = None
    category: IntervalCategory | None = None
    is_resolved: bool | None = None


class RecordingIntervalInfo(BaseModel):
    recording_id: int
    recording_title: str | None
    interval_id: int
    start_time: time
    end_time: time
    description: str
    category: IntervalCategory

    class Config:
        from_attributes = True


class IssueResponse(BaseModel):
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
    deleted_at: datetime | None

    class Config:
        from_attributes = True


class IssueWithIntervalsResponse(IssueResponse):
    recording_intervals: list[RecordingIntervalInfo] = []

    class Config:
        from_attributes = True 