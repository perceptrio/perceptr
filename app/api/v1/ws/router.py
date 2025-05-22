from typing import Dict

from common.services.logger import logger
from database import get_db
from fastapi import APIRouter, Depends, WebSocket
from requests import Session

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
