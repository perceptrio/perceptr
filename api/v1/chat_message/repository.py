from datetime import datetime

from models.chat_message import ChatMessage
from sqlalchemy.orm import Session


class ChatMessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, message: ChatMessage) -> ChatMessage:
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_by_id(self, message_id: int, chat_id: int) -> ChatMessage | None:
        return (
            self.db.query(ChatMessage)
            .filter(
                ChatMessage.id == message_id,
                ChatMessage.chat_id == chat_id,
                ChatMessage.deleted_at == None,
            )
            .first()
        )

    def get_all(
        self, chat_id: int, skip: int = 0, limit: int = 100
    ) -> list[ChatMessage]:
        return (
            self.db.query(ChatMessage)
            .filter(ChatMessage.chat_id == chat_id, ChatMessage.deleted_at == None)
            .order_by(ChatMessage.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def update(self, message: ChatMessage) -> ChatMessage:
        self.db.commit()
        self.db.refresh(message)
        return message

    def soft_delete(self, message: ChatMessage) -> ChatMessage:
        message.deleted_at = datetime.now()
        self.db.commit()
        self.db.refresh(message)
        return message
