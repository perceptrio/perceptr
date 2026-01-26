from models.chat_message import ChatMessage
from requests import Session

from .repository import ChatMessageRepository
from .schema import ChatMessageCreate, ChatMessageUpdate


def send_message(db: Session, message: ChatMessageCreate) -> ChatMessage:
    repo = ChatMessageRepository(db)
    message = ChatMessage(
        chat_id=message.chat_id,
        type="user",
        data={"query": message.query},
    )
    # TODO: hook with graph
    return repo.create(message)


def get_message(db: Session, message_id: int, chat_id: int) -> ChatMessage:
    repo = ChatMessageRepository(db)
    message = repo.get_by_id(message_id, chat_id)
    if not message:
        raise Exception("Message not found")
    return message


def get_messages(
    db: Session, chat_id: int, skip: int = 0, limit: int = 100
) -> list[ChatMessage]:
    repo = ChatMessageRepository(db)
    return repo.get_all(chat_id, skip, limit)


def update_message(
    db: Session, message_id: int, chat_id: int, message_update: ChatMessageUpdate
) -> ChatMessage:
    repo = ChatMessageRepository(db)
    message = repo.get_by_id(message_id, chat_id)
    if not message:
        raise Exception("Message not found")
    if message_update.text is not None:
        message.text = message_update.text
    if message_update.data is not None:
        message.data = message_update.data
    return repo.update(message)


def soft_delete_message(db: Session, message_id: int, chat_id: int) -> ChatMessage:
    repo = ChatMessageRepository(db)
    message = repo.get_by_id(message_id, chat_id)
    return repo.soft_delete(message)
