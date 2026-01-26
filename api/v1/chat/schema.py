from pydantic import BaseModel


class ChatCreate(BaseModel):
    title: str


class ChatUpdate(BaseModel):
    title: str | None = None
