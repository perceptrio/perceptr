from datetime import datetime
from sqlalchemy.orm import Session
from models.recording import Recording


class RecordingRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, recording: Recording) -> Recording:
        self.db.add(recording)
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def get_by_id(self, recording_id: int, org_id: int) -> Recording | None:
        return (
            self.db.query(Recording)
            .filter(Recording.id == recording_id, Recording.org_id == org_id)
            .first()
        )

    def get_all(
        self,
        org_id: int,
        skip: int = 0,
        limit: int = 100,
        search: str = None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> list[Recording]:
        query = self.db.query(Recording).filter(
            Recording.org_id == org_id, Recording.deleted_at == None
        )
        if search:
            query = query.filter(
                (Recording.file_name.ilike(f"%{search}%"))
                | (Recording.short_title.ilike(f"%{search}%"))
                | (Recording.summary.ilike(f"%{search}%"))
            )
        if start_date:
            query = query.filter(Recording.created_at >= start_date)
        if end_date:
            query = query.filter(Recording.created_at <= end_date)
        return (
            query.order_by(Recording.created_at.desc()).offset(skip).limit(limit).all()
        )

    def get_recording_by_session_id(self, session_id: str, org_id: int) -> Recording:
        return (
            self.db.query(Recording)
            .filter(
                Recording.session_id == session_id,
                Recording.org_id == org_id,
                Recording.deleted_at == None,
            )
            .first()
        )

    def update(self, recording: Recording) -> Recording:
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def soft_delete(self, recording: Recording) -> None:
        recording.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(recording)
        return recording

    def delete(self, recording: Recording) -> None:
        self.db.delete(recording)
        self.db.commit()
