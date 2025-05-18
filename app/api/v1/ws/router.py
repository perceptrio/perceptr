from typing import Dict

from api.v1.chat import service as chat_service
from api.v1.chat_message import service as chat_message_service
from common.services.logger import logger
from database import get_db
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from requests import Session
from utils.auth import validate_org_token

from app.api.v1.chat.schema import ChatCreate
from app.api.v1.chat_message.schema import ChatMessageCreate

from . import service as ws_service

router = APIRouter(prefix="/ws", tags=["ws"])

active_connections: Dict[str, WebSocket] = {}
PING_INTERVAL = 30  # seconds
PONG_TIMEOUT = 10  # seconds


def get_token_from_header(websocket: WebSocket) -> str | None:
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        return None
    if not auth_header.lower().startswith("bearer "):
        return None
    return auth_header[7:]


@router.websocket_route("/ws", name="ws")
async def websocket_handler(websocket: WebSocket, db: Session = Depends(get_db)):
    await ws_service.handle_websocket(websocket, db)
