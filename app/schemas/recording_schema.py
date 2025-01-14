from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class RecordingAnalysis(BaseModel):
    user_id: str
    recording_id: str
    recording_path: str
