from datetime import UTC, datetime, timedelta
from typing import List, Optional

from common.enums import AnalysisStatus
from models.recording import Recording
from settings import settings
from sqlalchemy.orm import Session


class RecordingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, recording: Recording) -> Recording:
        self.db.add(recording)
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def get_by_id(self, recording_id: int, org_id: int) -> Optional[Recording]:
        return (
            self.db.query(Recording)
            .filter(Recording.id == recording_id, Recording.org_id == org_id)
            .first()
        )

    def get_stale_sessions(self) -> List[Recording]:
        return (
            self.db.query(Recording)
            .filter(
                Recording.updated_at
                < datetime.now(UTC)
                - timedelta(seconds=settings.STALE_SESSION_DURATION),
                Recording.analysis_status == AnalysisStatus.PENDING.value,
            )
            .all()
        )

    def get_all(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 100,
        search: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> List[Recording]:
        query = self.db.query(Recording).filter(
            Recording.org_id == org_id, Recording.deleted_at == None  # noqa: E711
        )
        if search:
            query = query.filter(
                (Recording.file_name.ilike(f"%{search}%"))
                | (Recording.short_title.ilike(f"%{search.lower()}%"))
                | (Recording.summary.ilike(f"%{search.lower()}%"))
            )
        if start_date:
            query = query.filter(Recording.created_at >= start_date)
        if end_date:
            query = query.filter(Recording.created_at <= end_date)

        result = (
            query.order_by(Recording.created_at.desc()).offset(skip).limit(limit).all()
        )
        return result  # type: ignore

    def get_recording_by_session_id(
        self, session_id: str, org_id: int
    ) -> Optional[Recording]:
        return (
            self.db.query(Recording)
            .filter(
                Recording.session_id == session_id,
                Recording.org_id == org_id,
                Recording.deleted_at == None,  # noqa: E711
            )
            .first()
        )

    def update(self, recording: Recording) -> Recording:
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def upsert(self, recording: Recording) -> Recording:
        self.db.add(recording)
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def soft_delete(self, recording: Recording) -> Recording:
        recording.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def delete(self, recording: Recording) -> None:
        self.db.delete(recording)
        self.db.commit()
