from typing import Literal
from pydantic import BaseModel


class TokenPayload(BaseModel):
    org_id: str

class AdminTokenPayload(TokenPayload):
    admin_id: str
    admin_type: Literal["ADMIN", "SUPER_ADMIN"]
