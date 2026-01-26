from datetime import datetime

from models.chat import Chat
from models.chat_message import ChatMessage
from sqlalchemy.orm import Session


class ChatRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, chat: Chat) -> Chat:
        self.db.add(chat)
        self.db.commit()
        self.db.refresh(chat)
        return chat

    def get_by_id(self, chat_id: int, org_id: int) -> Chat | None:
        return (
            self.db.query(Chat)
            .filter(Chat.id == chat_id, Chat.org_id == org_id, Chat.deleted_at == None)
            .first()
        )

    def get_all(self, org_id: int, skip: int = 0, limit: int = 100) -> list[Chat]:
        return (
            self.db.query(Chat)
            .filter(Chat.org_id == org_id, Chat.deleted_at == None)
            .order_by(Chat.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, chat: Chat) -> Chat:
        self.db.commit()
        self.db.refresh(chat)
        return chat

    def soft_delete(self, chat: Chat) -> Chat:
        chat.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(chat)
        return chat
