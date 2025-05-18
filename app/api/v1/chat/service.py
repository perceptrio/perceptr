from models.chat import Chat
from sqlalchemy.orm import Session

from .repository import ChatRepository
from .schema import ChatCreate, ChatUpdate


def create_chat(db: Session, org_id: int, chat: ChatCreate) -> Chat:
    repo = ChatRepository(db)
    chat = Chat(org_id=org_id, title=chat.title)
    return repo.create(chat)


def get_chat(db: Session, chat_id: int, org_id: int) -> Chat:
    repo = ChatRepository(db)
    chat = repo.get_by_id(chat_id, org_id)
    if not chat:
        raise Exception("Chat not found")
    return chat


def get_chats(db: Session, org_id: int, skip: int = 0, limit: int = 100) -> list[Chat]:
    repo = ChatRepository(db)
    return repo.get_all(org_id, skip, limit)


def update_chat(
    db: Session, chat_id: int, org_id: int, chat_update: ChatUpdate
) -> Chat:
    repo = ChatRepository(db)
    chat = repo.get_by_id(chat_id, org_id)
    if not chat:
        raise Exception("Chat not found")
    if chat_update.title is not None:
        chat.title = chat_update.title
    return repo.update(chat)


def soft_delete_chat(db: Session, chat_id: int, org_id: int) -> Chat:
    repo = ChatRepository(db)
    chat = repo.get_by_id(chat_id, org_id)
    if not chat:
        raise Exception("Chat not found")
    return repo.soft_delete(chat)
