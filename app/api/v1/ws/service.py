from typing import Dict, Optional

from api.v1.chat import service as chat_service
from api.v1.chat_message import service as chat_message_service
from common.services.logger import logger
from fastapi import WebSocket, WebSocketDisconnect, status
from utils.auth import validate_org_token

from app.api.v1.chat.schema import ChatCreate
from app.api.v1.chat_message.schema import ChatMessageCreate

# Maps org_id to WebSocket
active_connections: Dict[str, WebSocket] = {}


def get_token_from_header(websocket: WebSocket) -> Optional[str]:
    auth_header = websocket.headers.get("authorization")
    if not auth_header:
        return None
    if not auth_header.lower().startswith("bearer "):
        return None
    return auth_header[7:]


async def handle_websocket(websocket: WebSocket, db):
    client_ip = websocket.client.host
    token = get_token_from_header(websocket)
    if not token:
        logger.error("No token provided for websocket connection", client_ip=client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    try:
        org_id = await validate_org_token(token)
    except Exception as e:
        logger.error("Invalid token", exc_info=e, client_ip=client_ip)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(e))
        return
    if org_id in active_connections:
        logger.warning(
            "WebSocket connection already established",
            org_id=org_id,
            client_ip=client_ip,
        )
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Only one connection per org allowed.",
        )
        return
    await websocket.accept()
    active_connections[org_id] = websocket
    logger.info(
        "WebSocket connection established",
        org_id=org_id,
        client_ip=client_ip,
    )
    try:
        while True:
            data = await websocket.receive_json()
            response = await process_message(data, db, org_id)
            await websocket.send_json(response)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", org_id=org_id, client_ip=client_ip)
    except Exception as e:
        logger.error("WebSocket error", exc_info=e)
        await websocket.close(
            code=status.WS_1011_INTERNAL_ERROR, reason="Internal error"
        )
    finally:
        if org_id in active_connections:
            del active_connections[org_id]


def get_websocket_by_org_id(org_id: str) -> Optional[WebSocket]:
    return active_connections.get(org_id)


async def send_message_to_org(org_id: str, ws_message: dict):
    ws = get_websocket_by_org_id(org_id)
    if ws:
        await ws.send_json(ws_message)
        return True
    return False


async def process_message(data: dict, db, org_id: str) -> dict:
    try:
        service = data.get("service")
        if service == "chat":
            message_type = data.get("type")
            if message_type == "getChats":
                chats = chat_service.get_chats(db, org_id)
                return {
                    "type": "getChats",
                    "chats": [chat.__dict__ for chat in chats],
                }
        elif service == "message":
            chat_id = data.get("chat_id")
            message_type = data.get("type")
            if message_type == "getMessages":
                skip = data.get("skip", 0)
                limit = data.get("limit", 100)
                messages = chat_message_service.get_messages(db, chat_id, skip, limit)
                return {
                    "type": "getMessages",
                    "messages": [message.__dict__ for message in messages],
                }
            elif message_type == "sendMessage":
                query = data.get("query")
                is_new_chat = data.get("is_new_chat", False)
                if not query:
                    return {
                        "type": "error",
                        "error": "query is required",
                    }
                if is_new_chat:
                    chat = chat_service.create_chat(db, org_id, ChatCreate(title=query))
                    chat_id = chat.id
                message = chat_message_service.send_message(
                    db, ChatMessageCreate(chat_id=chat_id, query=query)
                )
                return {
                    "type": "sendMessage",
                    "message": message.__dict__,
                }
        return {"error": "Invalid service"}
    except Exception as e:
        logger.error("Error processing message", exc_info=e)
        return {"error": "failed to process message"}
