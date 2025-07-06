"""Knowledge Graph processing API router."""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, status, Query
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from api.v1.kg import service
from api.v1.kg.schema import (
    BatchProcessRequest, ProcessingStatusResponse,
    CypherQuery, NaturalLanguageQuery, QueryResponse, AnalyticsResponse
)
from common.middleware.auth_token import GetPayload
from common.services.logger import logger
from common.types import TokenPayload
from core.constants import APIPath
from database import get_db
from kg.episodes import ENTITY_TYPES
from settings import settings
from api.v1.recording.service import check_recording_belonging_to_org

router = APIRouter(prefix=f"{APIPath.V1}/kg", tags=["knowledge-graph"])


@router.post("/setup", response_model=Dict[str, Any])
async def setup_kg_database(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
) -> Dict[str, Any]:
    """Initialize the Knowledge Graph database with constraints and indexes."""
    try:
        logger.info(f"Setting up KG database for org {payload.org.id}")
        
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.setup_kg_database(payload.org.id)
        
        if result['success']:
            logger.info(f"KG database setup completed for org {payload.org.id}")
            return {
                "success": True,
                "message": "Knowledge Graph database setup completed",
                "org_id": payload.org.id,
                "setup_details": result
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database setup failed: {result.get('error', 'Unknown error')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KG database setup failed for org {payload.org.id}: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database setup failed: {str(e)}"
        )


@router.get("/stats", response_model=Dict[str, Any])
async def get_kg_stats(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
) -> Dict[str, Any]:
    """Get Knowledge Graph statistics for the organization."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.get_kg_stats(payload.org.id)
        
        return {
            "success": True,
            "org_id": payload.org.id,
            "org_stats": result.get("org_stats", {}),
            "database_stats": result.get("database_stats", {}),
            "entity_types_supported": list(ENTITY_TYPES.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get KG stats for org {payload.org.id}: {str(e)}", exc_info=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get statistics: {str(e)}"
        )


@router.get("/extract/{recording_id}", response_model=ProcessingStatusResponse)
async def extract_kg_from_recording(
    recording_id: int,
    background_tasks: BackgroundTasks,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
) -> ProcessingStatusResponse:
    """Extract Knowledge Graph data from a specific recording.
    
    The service will automatically download session batches from S3,
    consolidate them, and process the merged data for KG extraction.
    """
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        # Validate recording exists and has session_id before starting background task
        recording = check_recording_belonging_to_org(db, recording_id, payload.org.id)
        
        if not recording.session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Recording {recording_id} does not have a session_id and cannot be processed for KG extraction"
            )
        
        # Generate processing ID for tracking
        processing_id = f"kg_extract_{payload.org.id}_{recording_id}_{int(datetime.now().timestamp())}"
        
        # Start background processing
        background_tasks.add_task(
            service.process_recording_background,
            recording_id,
            payload.org.id,
            processing_id,
            db
        )
        
        logger.info(
            f"Started KG extraction for recording {recording_id}",
            org_id=payload.org.id,
            processing_id=processing_id,
            session_id=recording.session_id
        )
        
        return ProcessingStatusResponse(
            success=True,
            message=f"Knowledge Graph extraction started for recording {recording_id}",
            processing_id=processing_id,
            estimated_completion=datetime.now().replace(microsecond=0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to start KG extraction for recording {recording_id}",
            org_id=payload.org.id,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start extraction: {str(e)}"
        )


@router.post("/extract/batch", response_model=ProcessingStatusResponse)
async def extract_kg_batch(
    request: BatchProcessRequest,
    background_tasks: BackgroundTasks,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
) -> ProcessingStatusResponse:
    """Extract Knowledge Graph data from multiple recordings in batch.
    
    The service will automatically download session batches from S3,
    consolidate them, and process the merged data for KG extraction.
    """
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        if len(request.recording_ids) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Batch size cannot exceed 100 recordings"
            )
        
        # Validate recordings exist and have session_ids before starting background task
        invalid_recordings = []
        valid_recordings = []
        
        for recording_id in request.recording_ids:
            try:
                recording = check_recording_belonging_to_org(db, recording_id, payload.org.id)
                if not recording.session_id:
                    invalid_recordings.append(recording_id)
                else:
                    valid_recordings.append(recording_id)
            except HTTPException:
                invalid_recordings.append(recording_id)
        
        if invalid_recordings:
            if not valid_recordings:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No valid recordings found. Invalid recording IDs or recordings without session_id: {invalid_recordings}"
                )
            else:
                logger.warning(
                    f"Some recordings are invalid and will be skipped",
                    org_id=payload.org.id,
                    invalid_recordings=invalid_recordings,
                    valid_recordings=valid_recordings
                )
        
        # Generate processing ID for tracking
        processing_id = f"kg_batch_{payload.org.id}_{len(valid_recordings)}_{int(datetime.now().timestamp())}"
        
        # Start background batch processing with only valid recordings
        background_tasks.add_task(
            service.process_batch_background,
            valid_recordings,
            payload.org.id,
            processing_id,
            db
        )
        
        logger.info(
            f"Started batch KG extraction for {len(valid_recordings)} recordings",
            org_id=payload.org.id,
            processing_id=processing_id,
            valid_count=len(valid_recordings),
            invalid_count=len(invalid_recordings)
        )
        
        # Estimate completion time (rough estimate: 30 seconds per recording)
        estimated_seconds = len(valid_recordings) * 30
        estimated_completion = datetime.now().replace(microsecond=0)
        estimated_completion = estimated_completion.replace(second=estimated_completion.second + estimated_seconds)
        
        message = f"Batch Knowledge Graph extraction started for {len(valid_recordings)} recordings"
        if invalid_recordings:
            message += f". {len(invalid_recordings)} recordings were skipped due to missing session_id or invalid IDs."
        
        return ProcessingStatusResponse(
            success=True,
            message=message,
            processing_id=processing_id,
            estimated_completion=estimated_completion
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to start batch KG extraction",
            org_id=payload.org.id,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start batch extraction: {str(e)}"
        )


@router.post("/cypher", response_model=QueryResponse)
async def execute_cypher(
    query: CypherQuery,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
):
    """Execute Cypher queries with org isolation."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.execute_cypher_query(
            query.query, 
            query.parameters, 
            payload.org.id
        )
        
        return QueryResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Cypher query endpoint failed",
            org_id=payload.org.id,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query execution failed: {str(e)}"
        )


@router.post("/search", response_model=QueryResponse)
async def hybrid_search(
    query: NaturalLanguageQuery,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
):
    """Perform hybrid search using Graphiti."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.perform_hybrid_search(
            query.question,
            query.top_k,
            payload.org.id
        )
        
        return QueryResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Hybrid search endpoint failed",
            org_id=payload.org.id,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get("/analytics/sessions/{session_id}/journey", response_model=AnalyticsResponse)
async def get_session_journey(
    session_id: str,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
):
    """Get complete user journey for a session."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.get_session_journey(session_id, payload.org.id)
        
        return AnalyticsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Session journey endpoint failed",
            org_id=payload.org.id,
            session_id=session_id,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Journey analysis failed: {str(e)}"
        )


@router.get("/analytics/conversion/abandoned-carts", response_model=AnalyticsResponse)
async def get_abandoned_carts(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    hours_back: int = Query(24, description="Hours to look back"),
):
    """Find sessions that added to cart but never completed checkout."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.get_abandoned_carts(payload.org.id, hours_back)
        
        return AnalyticsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Abandoned carts endpoint failed",
            org_id=payload.org.id,
            hours_back=hours_back,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Abandoned cart analysis failed: {str(e)}"
        )


@router.get("/analytics/conversion/funnel", response_model=AnalyticsResponse)
async def analyze_conversion_funnel(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    steps: str = Query(..., description="Comma-separated funnel steps"),
    days_back: int = Query(7, description="Days to analyze"),
):
    """Analyze conversion funnel with abandonment points."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.analyze_conversion_funnel(payload.org.id, steps, days_back)
        
        return AnalyticsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Conversion funnel endpoint failed",
            org_id=payload.org.id,
            steps=steps,
            days_back=days_back,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Funnel analysis failed: {str(e)}"
        )


@router.get("/analytics/elements/popular", response_model=AnalyticsResponse)
async def get_popular_elements(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    hours_back: int = Query(24, description="Hours to analyze"),
    limit: int = Query(20, description="Number of top elements to return"),
):
    """Get most clicked elements in the given time period."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.get_popular_elements(payload.org.id, hours_back, limit)
        
        return AnalyticsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Popular elements endpoint failed",
            org_id=payload.org.id,
            hours_back=hours_back,
            limit=limit,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Popular elements analysis failed: {str(e)}"
        )


@router.get("/analytics/sessions/rage-clicks", response_model=AnalyticsResponse)
async def detect_rage_clicks(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    hours_back: int = Query(24, description="Hours to analyze"),
    min_clicks: int = Query(5, description="Minimum clicks to consider rage clicking"),
    time_window_seconds: int = Query(10, description="Time window for rapid clicks"),
):
    """Detect potential rage clicking patterns."""
    try:
        if not settings.KG_ENABLED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Knowledge Graph feature is disabled"
            )
        
        result = await service.detect_rage_clicks(
            payload.org.id, 
            hours_back, 
            min_clicks, 
            time_window_seconds
        )
        
        return AnalyticsResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Rage clicks endpoint failed",
            org_id=payload.org.id,
            hours_back=hours_back,
            min_clicks=min_clicks,
            time_window_seconds=time_window_seconds,
            error=str(e),
            exc_info=e
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rage click detection failed: {str(e)}"
        ) 