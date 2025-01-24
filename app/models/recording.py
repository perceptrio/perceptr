from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime, UTC
from .base import Base
from common.enums import AnalysisStatus
class Recording(Base):
    __tablename__ = 'recording'
    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(Integer, ForeignKey('org.id'), nullable=False)
    file_name = Column(String(250), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)
    analysis_status = Column(String(50), nullable=False, default=AnalysisStatus.PENDING.value)
    analysis_error = Column(String(250), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    deleted_at = Column(DateTime, nullable=True)

    def set_analysis_status(self, status: AnalysisStatus):
        self.analysis_status = status.value

    def get_analysis_status(self) -> AnalysisStatus:
        return AnalysisStatus(self.analysis_status)