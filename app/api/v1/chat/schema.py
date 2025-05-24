from pydantic import BaseModel


class ChatCreate(BaseModel):
    title: str


class ChatUpdate(BaseModel):
    title: str | None = None


class DiscoverRequest(BaseModel):
    query: str
    chat_id: int | None = None


class ChatMessageResponse(BaseModel):
    id: int
    type: str
    data: dict
    created_at: str | None
    
    class Config:
        from_attributes = True


class DiscoverResponse(BaseModel):
    chat_id: int
    messages: list[ChatMessageResponse]
    
    class Config:
        from_attributes = True
