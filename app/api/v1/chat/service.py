class ChatService:
    def __init__(self, org_id: int):
        self.org_id = org_id

    async def process_message(
        self, chat_id: str, message_type: str, data: dict
    ) -> dict:
        if message_type == "getMessages":
            # TODO: Fetch messages from storage
            return {
                "type": "getMessages",
                "messages": [{"from": "ai", "text": "Welcome!"}],
            }
        elif message_type == "sendMessage":
            # TODO: Store message and get AI response
            user_text = data.get("text", "")
            ai_response = f"AI: {user_text}"
            return {"type": "message", "from": "ai", "text": ai_response}
        else:
            return {"type": "error", "error": "Unknown message type"}
