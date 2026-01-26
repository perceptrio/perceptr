from typing import List, Optional

from pydantic import BaseModel, EmailStr


class LeadAIEngineerRequest(BaseModel):
    email: EmailStr
    role: str
    companySize: str
    useCases: List[str]
    utm: dict


class LeadUXAuditRequest(BaseModel):
    email: EmailStr


class UXAuditRequest(BaseModel):
    email: EmailStr
    key: str


class UXAuditResponse(BaseModel):
    message: str
    pdf_path: Optional[str] = None
    success: bool = True


class UXAuditSyncResponse(BaseModel):
    message: str
    pdf_path: str
    frames_analyzed: int
    success: bool = True


class UploadRequest(BaseModel):
    fileName: str
    fileType: str
    email: EmailStr


class UploadResponse(BaseModel):
    upload_url: str
    file_path: str
    message: str
    success: bool
