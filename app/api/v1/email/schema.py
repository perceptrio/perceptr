from typing import Optional

from pydantic import BaseModel, EmailStr


class EmailRequest(BaseModel):
    name: str
    email: EmailStr
    company: Optional[str] = None
    details: Optional[str] = None
    website: Optional[str] = None  # Honeypot field
