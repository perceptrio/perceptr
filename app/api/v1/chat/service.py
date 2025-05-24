from models.chat import Chat
from models.chat_message import ChatMessage
from sqlalchemy.orm import Session
from graphs.discover_graph import DiscoverGraph
from langgraph.checkpoint.memory import MemorySaver
from api.v1.chat_message.repository import ChatMessageRepository
from common.services.logger import logger
from utils.graph import convert_chat_messages_to_langchain_messages
from common.services.qdrant import Qdrant
from .repository import ChatRepository
from .schema import ChatCreate, ChatUpdate, DiscoverRequest

memory = MemorySaver()

def create_chat(db: Session, org_id: int, chat: ChatCreate) -> Chat:
    repo = ChatRepository(db)
    chat = Chat(org_id=org_id, title=chat.title)
    return repo.create(chat)


def get_chat(db: Session, chat_id: int, org_id: int) -> Chat:
    repo = ChatRepository(db)
    chat = repo.get_by_id(chat_id, org_id)
    if not chat:
        raise Exception("Chat not found")
    return chat


def get_chats(db: Session, org_id: int, skip: int = 0, limit: int = 100) -> list[Chat]:
    repo = ChatRepository(db)
    return repo.get_all(org_id, skip, limit)


def update_chat(
    db: Session, chat_id: int, org_id: int, chat_update: ChatUpdate
) -> Chat:
    repo = ChatRepository(db)
    chat = repo.get_by_id(chat_id, org_id)
    if not chat:
        raise Exception("Chat not found")
    if chat_update.title is not None:
        chat.title = chat_update.title
    return repo.update(chat)


def soft_delete_chat(db: Session, chat_id: int, org_id: int) -> Chat:
    repo = ChatRepository(db)
    chat = repo.get_by_id(chat_id, org_id)
    if not chat:
        raise Exception("Chat not found")
    return repo.soft_delete(chat)


def discover(db: Session, org_id: int, request: DiscoverRequest) -> dict:
    """
    Process a discover request: create/get chat, save user message, invoke discover graph,
    save assistant response, and return the results.
    """
    chat_repo = ChatRepository(db)
    message_repo = ChatMessageRepository(db)
    
    # Get or create chat
    if request.chat_id:
        chat = chat_repo.get_by_id(request.chat_id, org_id)
        if not chat:
            raise Exception("Chat not found")
    else:
        # Create new chat with query as title (truncated if too long)
        title = request.query[:100] + "..." if len(request.query) > 100 else request.query
        chat_create = ChatCreate(title=title)
        chat = create_chat(db, org_id, chat_create)
    
    # Save user message
    user_message = ChatMessage(
        chat_id=chat.id,
        type="user",
        data={"query": request.query}
    )
    user_message = message_repo.create(user_message)

    chat_messages = message_repo.get_all(chat.id)
    langchain_messages = convert_chat_messages_to_langchain_messages(chat_messages)

    qdrant = Qdrant(collection_name="sessions")
    total_num_sessions = qdrant.get_count(org_id)
    
    # Initialize and invoke discover graph
    discover_graph = DiscoverGraph(memory=memory)
    
    try:
        # Invoke the discover graph
        graph_response = discover_graph.discover(
            org_id=org_id,
            chat_id=chat.id,
            messages=langchain_messages,
            total_num_sessions=total_num_sessions
        )
        
        # Extract the assistant response from the graph
        messages = graph_response.get("messages", [])
        structured_response = graph_response.get("structured_response", None)
        # assistant_content = messages[-1].content
        
        # Find the last assistant message in the response
        # for message in reversed(messages):
        #     if hasattr(message, 'type') and message.type == 'ai':
        #         assistant_content = message.content
        #         break
        
        # Convert LangChain messages to serializable format
        # serializable_messages = []
        # for message in messages:
        #     try:
        #         if hasattr(message, 'content') and hasattr(message, 'type'):
        #             # Ensure all values are JSON serializable
        #             additional_kwargs = getattr(message, 'additional_kwargs', {})
        #             if not isinstance(additional_kwargs, dict):
        #                 additional_kwargs = {}
                    
        #             message_id = getattr(message, 'id', None)
        #             if message_id and not isinstance(message_id, (str, int, type(None))):
        #                 message_id = str(message_id)
                    
        #             serializable_messages.append({
        #                 "type": str(message.type),
        #                 "content": str(message.content),
        #                 "additional_kwargs": additional_kwargs,
        #                 "id": message_id
        #             })
        #     except Exception as msg_error:
        #         logger.warning(f"Failed to serialize message: {msg_error}")
        #         # Add a fallback message
        #         serializable_messages.append({
        #             "type": "unknown",
        #             "content": "Message could not be serialized",
        #             "additional_kwargs": {},
        #             "id": None
        #         })
        
        # Save assistant message
        assistant_message = ChatMessage(
            chat_id=chat.id,
            type="markdown",
            data=structured_response.model_dump()
        )
        assistant_message = message_repo.create(assistant_message)
        
        return {
            "chat_id": chat.id,
            "messages": [
                {
                    "id": user_message.id,
                    "type": user_message.type,
                    "data": user_message.data,
                    "created_at": user_message.created_at.isoformat() if user_message.created_at else None
                },
                {
                    "id": assistant_message.id,
                    "type": assistant_message.type,
                    "data": assistant_message.data,
                    "created_at": assistant_message.created_at.isoformat() if assistant_message.created_at else None
                }
            ]
        }
        
    except Exception as e:
        # Rollback the database session to clean up any failed transactions
        db.rollback()
        logger.error(f"Error processing discover request: {str(e)}", exc_info=e)
        raise Exception(f"Error processing discover request: {str(e)}")
