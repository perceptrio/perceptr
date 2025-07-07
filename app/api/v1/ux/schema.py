from pydantic import BaseModel
from typing import Optional


class UXAuditRequest(BaseModel):
    email: str
    file_name: str


class UXAuditResponse(BaseModel):
    message: str
    pdf_path: Optional[str] = None
    success: bool = True


class UXAuditSyncResponse(BaseModel):
    message: str
    pdf_path: str
    frames_analyzed: int
    success: bool = True 