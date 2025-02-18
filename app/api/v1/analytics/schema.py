from pydantic import BaseModel


class KeyMetricsResponse(BaseModel):
    sessions_analyzed: int
    issues_found: int
    issues_resolved: int
    normal_sessions: int
