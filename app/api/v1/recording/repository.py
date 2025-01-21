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
        return self.db.query(Recording).filter(Recording.id == recording_id, Recording.org_id == org_id).first()


    def get_all(self, org_id: int, skip: int = 0, limit: int = 100) -> list[Recording]:
        return self.db.query(Recording).filter(Recording.org_id == org_id, Recording.deleted_at == None).offset(skip).limit(limit).all()

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
