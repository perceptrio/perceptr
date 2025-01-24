from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from models.recording_interval import RecordingInterval
from .repository import RecordingIntervalRepository
from .schema import RecordingIntervalCreate, RecordingIntervalUpdate

def create_recording_interval(db: Session, recording_interval: RecordingIntervalCreate) -> RecordingInterval:
    """Create a new recording interval"""
    
    # Create recording
    repository = RecordingIntervalRepository(db)
    recording_interval = repository.create(RecordingInterval(
        recording_id=recording_interval.recording_id,
        start_time=recording_interval.start_time,
        end_time=recording_interval.end_time,

    ))
    return recording_interval

def get_recording_interval(db: Session, recording_interval_id: int, recording_id: int) -> RecordingInterval:
    repository = RecordingIntervalRepository(db)
    recording_interval = repository.get_by_id(recording_interval_id, recording_id)
    if not recording_interval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recording not found"
        )
    return recording_interval

def get_recordings(db: Session, recording_id: int, skip: int = 0, limit: int = 100) -> list[RecordingInterval]:
    repository = RecordingIntervalRepository(db)
    return repository.get_all(recording_id, skip, limit)

def get_recording_intervals_by_recording_id(db: Session, recording_id: int) -> list[RecordingInterval]:
    repository = RecordingIntervalRepository(db)
    return repository.get_by_recording_id(recording_id)

def update_recording_interval(db: Session, recording_interval_id: int, recording_interval: RecordingIntervalUpdate) -> RecordingInterval:
    repository = RecordingIntervalRepository(db)
    return repository.update(recording_interval)

def soft_delete_recording_interval(db: Session, recording_interval_id: int, recording_id: int) -> None:
    repository = RecordingIntervalRepository(db)
    recording_interval = repository.get_by_id(recording_interval_id, recording_id)
    if not recording_interval:
        raise HTTPException(status_code=404, detail="Recording interval not found")
    repository.soft_delete(recording_interval)
    

def batch_create_recording_intervals(db: Session, recording_intervals: list[RecordingInterval]) -> list[RecordingInterval]:
    repository = RecordingIntervalRepository(db)
    return repository.batch_create(recording_intervals)

def replace_recording_intervals(db: Session, recording_id: int, recording_intervals: list[RecordingInterval]) -> list[RecordingInterval]:
    repository = RecordingIntervalRepository(db)
    repository.batch_delete_with_recording_id(recording_id)
    return repository.batch_create(recording_intervals)

def check_recording_intervals_with_recording_id(db: Session, recording_id: int) -> bool:
    repository = RecordingIntervalRepository(db)
    return repository.get_by_recording_id(recording_id) is not None