from pydantic import BaseModel
from typing import List, Dict, Any, Literal, Optional


class NetworkRequest(BaseModel):
    type: Literal[7]
    id: str
    timestamp: int
    video_timestamp: str
    duration: int
    method: str
    url: str
    status: Optional[int] = None
    statusText: Optional[str] = None
    requestHeaders: Dict[str, str]
    responseHeaders: Dict[str, str]
    requestBody: Optional[Any] = None
    responseBody: Optional[Any] = None
    error: Optional[Any] = None


class UserIdentity(BaseModel):
    distinctId: str
    email: Optional[str] = None
    name: Optional[str] = None
    model_config = {
        "extra": "allow"  # Allows additional fields not defined in the model
    }


class SnapshotBuffer(BaseModel):
    size: int
    data: List[Any]  # EventType (can be NetworkRequest or eventWithTime)
    isSessionEnded: bool
    startTime: int
    endTime: Optional[int] = None
    sessionId: str
    metadata: Optional[Dict[str, Any]] = None
    userIdentity: Optional[UserIdentity] = None


class GenericResponse(BaseModel):
    success: bool
    message: Optional[str] = None
