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


# Issue types matching heuristic categories
SIGNAL_RAGE_CLICK = "rage_click"
SIGNAL_DEAD_CLICK = "dead_click"
SIGNAL_NAVIGATION_LOOP = "navigation_loop"
SIGNAL_FORM_STRUGGLE = "form_struggle"
SIGNAL_SCROLL_THRASHING = "scroll_thrashing"
SIGNAL_UNKNOWN = "unknown"

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"
SEVERITY_CRITICAL = "critical"

# Category types matching video analyzer
CATEGORY_BUG = "BUG"
CATEGORY_USABILITY_ISSUE = "USABILITY_ISSUE"
CATEGORY_PERFORMANCE_ISSUE = "PERFORMANCE_ISSUE"
CATEGORY_ENHANCEMENT = "ENHANCEMENT"
