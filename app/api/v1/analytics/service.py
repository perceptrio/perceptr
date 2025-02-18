from sqlalchemy.orm import Session
from .repository import AnalyticsRepository
from .schema import KeyMetricsResponse


def get_key_metrics(db: Session, org_id: int) -> KeyMetricsResponse:
    repository = AnalyticsRepository(db)
    metrics = repository.get_key_metrics(org_id)
    return KeyMetricsResponse(**metrics)
