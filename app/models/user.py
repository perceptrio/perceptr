from sqlalchemy import Column, Integer, String, DateTime
import datetime
from .base import Base

class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False, unique=True)
    password = Column(String(250), nullable=False)
    joined_at = Column(DateTime, default=datetime.datetime.now)