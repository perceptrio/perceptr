from fastapi import APIRouter, Depends
from core.constants import APIPath
from .schema import KeyMetricsResponse
from . import service
from common.types import TokenPayload
from typing_extensions import Annotated
from common.middleware import GetPayload
from sqlalchemy.orm import Session
from database import get_db

router = APIRouter(prefix=f"{APIPath.V1}/analytics", tags=["analytics"])


@router.get("/key-metrics", response_model=KeyMetricsResponse)
def get_key_metrics(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    """Get key analytics metrics for the organization"""
    return service.get_key_metrics(db, payload.org.id)
