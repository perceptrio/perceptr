from datetime import datetime
from sqlalchemy.orm import Session
from models.recording_interval import RecordingInterval

class RecordingIntervalRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, recording_interval: RecordingInterval) -> RecordingInterval:
        self.db.add(recording_interval)
        self.db.commit()
        self.db.refresh(recording_interval)
        return recording_interval

    def get_by_id(self, recording_interval_id: int, recording_id: int) -> RecordingInterval | None:
        return self.db.query(RecordingInterval).filter(RecordingInterval.id == recording_interval_id, RecordingInterval.recording_id == recording_id).first()

    def get_by_recording_id(self, recording_id: int) -> list[RecordingInterval]:
        return self.db.query(RecordingInterval).filter(RecordingInterval.recording_id  == recording_id, RecordingInterval.deleted_at == None).all()

    def get_all(self, recording_id: int, skip: int = 0, limit: int = 100) -> list[RecordingInterval]:
        return self.db.query(RecordingInterval).filter(RecordingInterval.recording_id  == recording_id, RecordingInterval.deleted_at == None).offset(skip).limit(limit).all()

    def update(self, recording_interval: RecordingInterval) -> RecordingInterval:
        self.db.commit()
        self.db.refresh(recording_interval)
        return recording_interval

    def soft_delete(self, recording_interval: RecordingInterval) -> None:
        recording_interval.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(recording_interval)
        return recording_interval

    def delete(self, recording_interval: RecordingInterval) -> None:
        self.db.delete(recording_interval)
        self.db.commit()

    def batch_create(self, recording_intervals: list[RecordingInterval]) -> list[RecordingInterval]:
        self.db.add_all(recording_intervals)
        self.db.commit()
        return recording_intervals