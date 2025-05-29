from database import get_db
from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from . import service as ws_service

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket_route("/ws", name="ws")
async def websocket_handler(websocket: WebSocket, db: Session = Depends(get_db)):
    await ws_service.handle_websocket(websocket, db)
