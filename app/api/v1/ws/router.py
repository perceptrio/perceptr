from typing import Dict

from api.v1.chat.service import ChatService
from common.services.logger import logger
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from utils.auth import validate_org_token

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
async def websocket_handler(websocket: WebSocket):
    client_ip = websocket.client.host
    token = get_token_from_header(websocket)
    if not token:
        logger.error("No token provided for websocket connection", client_ip=client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    if client_ip in active_connections:
        logger.warning(
            "WebSocket connection already established",
            client_ip=client_ip,
        )
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Only one connection per IP allowed.",
        )
        return
    try:
        org_id = await validate_org_token(token)
    except Exception as e:
        logger.error("Invalid token", exc_info=e, client_ip=client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
        return
    await websocket.accept()
    active_connections[client_ip] = websocket
    logger.info(
        "WebSocket connection established",
        org_id=org_id,
        client_ip=client_ip,
    )
    chat_service = ChatService(org_id)
    try:
        while True:
            data = await websocket.receive_json()
            service = data.get("service")
            if service == "chat":
                chat_id = data.get("chat_id")
                message_type = data.get("type")
                response = await chat_service.process_message(
                    chat_id, message_type, data
                )
            else:
                response = {"error": "Invalid service"}
            await websocket.send_json(response)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", client_ip=client_ip)
    except Exception as e:
        logger.error("WebSocket error", exc_info=e)
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR, reason="Internal error"
        )
    finally:
        if client_ip in active_connections:
            del active_connections[client_ip]
