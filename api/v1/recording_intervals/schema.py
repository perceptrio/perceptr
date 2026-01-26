from datetime import time, datetime
from pydantic import BaseModel, field_validator
from typing import Dict, Any, Optional, List
from common.enums import IntervalCategory


class TimestampDescription(BaseModel):
    description: str
    timestamp: str


class RecordingIntervalBase(BaseModel):
    recording_id: int
    start_time: time
    end_time: time
    description: str
    category: IntervalCategory
    issue: Optional[str] = None
    short_title: str
    timestamp_descriptions: List[TimestampDescription]

    @field_validator("category", mode="before")
    def parse_category(cls, v):
        if isinstance(v, str):
            return IntervalCategory(v)
        return v


class RecordingIntervalCreate(RecordingIntervalBase):
    pass


class RecordingIntervalUpdate(BaseModel):
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    description: Optional[str] = None
    category: Optional[IntervalCategory] = None
    issue: Optional[str] = None
    short_title: Optional[str] = None
    timestamp_descriptions: Optional[Dict[str, Any]] = None


class RecordingIntervalResponse(RecordingIntervalBase):
    id: int
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    class Config:
        from_attributes = True  # Allows conversion from SQLAlchemy model
