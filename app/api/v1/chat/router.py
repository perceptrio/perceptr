from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing_extensions import Annotated
from common.middleware.auth_token import GetPayload
from common.types import TokenPayload
from core.constants import APIPath
from database import get_db

from . import service
from .schema import DiscoverRequest, DiscoverResponse, ChatCreate, ChatUpdate

router = APIRouter(prefix=f"{APIPath.V1}/chat", tags=["chat"])


@router.post("/discover", response_model=DiscoverResponse)
def discover(
    request: DiscoverRequest,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    """
    Process a discover query using the discover graph.
    Creates a new chat if chat_id is not provided.
    """
    try:
        result = service.discover(db, payload.org.id, request)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_chat(
    chat_create: ChatCreate,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    """Create a new chat"""
    try:
        chat = service.create_chat(db, payload.org.id, chat_create)
        return {
            "id": chat.id,
            "title": chat.title,
            "created_at": chat.created_at.isoformat() if chat.created_at else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{chat_id}")
def get_chat(
    chat_id: int,
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
):
    """Get a chat by ID"""
    try:
        chat = service.get_chat(db, chat_id, payload.org.id)
        return {
            "id": chat.id,
            "title": chat.title,
            "created_at": chat.created_at.isoformat() if chat.created_at else None,
            "updated_at": chat.updated_at.isoformat() if chat.updated_at else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/")
def get_chats(
    payload: Annotated[TokenPayload, Depends(GetPayload(type="access"))],
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """Get all chats for the organization"""
    try:
        chats = service.get_chats(db, payload.org.id, skip, limit)
        return [
            {
                "id": chat.id,
                "title": chat.title,
                "created_at": chat.created_at.isoformat() if chat.created_at else None,
                "updated_at": chat.updated_at.isoformat() if chat.updated_at else None
            }
            for chat in chats
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
