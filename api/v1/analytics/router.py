from common.middleware.auth_token import GetPayload
from common.types import TokenPayload
from core.constants import APIPath
from database import get_db
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing_extensions import Annotated

from . import service
from .schema import KeyMetricsResponse

router = APIRouter(prefix=f"{APIPath.V1}/analytics", tags=["analytics"])


@router.get("/key-metrics", response_model=KeyMetricsResponse)
def get_key_metrics(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    """Get key analytics metrics for the organization"""
    return service.get_key_metrics(db, payload.org.id)
