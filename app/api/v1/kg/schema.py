"""Knowledge Graph API schemas."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class BatchProcessRequest(BaseModel):
    """Request to batch process multiple recordings for KG extraction.
    
    The service will automatically download session batches from S3,
    consolidate them, and process the merged data for KG extraction.
    Recordings without session_id will be skipped automatically.
    """
    recording_ids: List[int] = Field(..., description="List of recording IDs to process")


class ProcessingStatusResponse(BaseModel):
    """Response for processing status."""
    success: bool
    message: str
    processing_id: Optional[str] = None
    estimated_completion: Optional[datetime] = None


class CypherQuery(BaseModel):
    """Cypher query request model."""
    query: str
    parameters: Optional[Dict[str, Any]] = {}


class NaturalLanguageQuery(BaseModel):
    """Natural language query request model."""
    question: str
    top_k: int = 100


class QueryResponse(BaseModel):
    """Query response model."""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    query_time_ms: Optional[float] = None


class UserJourneyResponse(BaseModel):
    """User journey response model."""
    session_id: str
    user_id: str
    pages: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    duration: float
    conversion_events: List[Dict[str, Any]]


class ConversionFunnelResponse(BaseModel):
    """Conversion funnel response model."""
    step_name: str
    users_entered: int
    users_completed: int
    conversion_rate: float
    drop_off_rate: float


class AnalyticsResponse(BaseModel):
    """Generic analytics response model."""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    query_time_ms: Optional[float] = None
    total_count: Optional[int] = None 