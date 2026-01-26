from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    chat_id: int
    query: str


class ChatMessageUpdate(BaseModel):
    query: str | None = None
