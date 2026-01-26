from typing import Literal
from pydantic import BaseModel


class AbstractOrg(BaseModel):
    id: int
    name: str
    email: str

class TokenPayload(BaseModel):
    org: AbstractOrg

class CreateTokenPayload(BaseModel):
    org_id: int

class AdminTokenPayload(TokenPayload):
    admin_id: str
    admin_type: Literal["ADMIN", "SUPER_ADMIN"]
