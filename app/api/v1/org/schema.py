from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class OrgBase(BaseModel):
    name: str
    email: EmailStr

class OrgCreate(OrgBase):
    password: str

class OrgLogin(BaseModel):
    email: EmailStr
    password: str

class OrgUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

class OrgResponse(OrgBase):
    id: int
    joined_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str