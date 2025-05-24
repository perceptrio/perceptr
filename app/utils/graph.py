from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from models.chat_message import ChatMessage

def convert_chat_messages_to_langchain_messages(chat_messages: list[ChatMessage]) -> list[BaseMessage]:
    langchain_messages = []
    for chat_message in chat_messages:
        if chat_message.type == "user":
            langchain_messages.append(HumanMessage(content=chat_message.data["query"]))
        elif chat_message.type == "markdown":
            langchain_messages.append(AIMessage(content=chat_message.data["content"]))
    return langchain_messages