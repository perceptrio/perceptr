from typing import Optional
from pydantic import BaseModel

from common.enums import IntervalCategory

class RecordingIntervalCreate(BaseModel):
    recording_id: int
    start_time: int
    end_time: int
    summary: str
    category: IntervalCategory
    issue: str

class RecordingIntervalUpdate(BaseModel):
    start_time: Optional[int]
    end_time: Optional[int]
    summary: Optional[str]
    category: Optional[IntervalCategory]
    issue: Optional[str]