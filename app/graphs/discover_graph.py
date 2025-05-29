import os
from typing import Any, Dict, List, Annotated, Optional
from datetime import datetime
from common.services.logger import logger
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langfuse.decorators import langfuse_context, observe
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from settings import settings
from typing_extensions import TypedDict
from tools.discover_tools import filter_sessions
from pydantic import BaseModel, Field

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

class Response(BaseModel):
    response: str = Field(description="The response to the user's query")
    session_ids: Optional[list[int]] = Field(description="The ids of the sessions that are relevant to the user's query, if any. You can find the session ids in the metadata of the sessions as session_id.")
    issues_ids: Optional[list[int]] = Field(description="The ids of the issues that are relevant to the user's query, if any. You can find the issue ids in the metadata of the issues as issue_id.")

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    structured_response: Response


class DiscoverGraph:
    def __init__(self, memory: MemorySaver) -> None:
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4.1-mini",
            streaming=True,
            temperature=0,
        )
        self.gemini_llm = ChatGoogleGenerativeAI(
            api_key=settings.GEMINI_API_KEY,
            # model="gemini-2.5-pro-preview-05-06",
            model="gemini-2.5-flash-preview-05-20",
            streaming=True,
            temperature=0.2,
        )
        
        graph_builder.add_node("discover_node", self.discover_node)
        graph_builder.add_edge(START, "discover_node")
        graph_builder.add_edge("discover_node", END)
        self.graph = graph_builder.compile(checkpointer=memory)

    def discover_node(self, state: State, config: RunnableConfig) -> dict:
        # Create react agent with filter_sessions tool

        total_num_sessions = config.get("configurable", {}).get("total_num_sessions")

        system_prompt = f"""
        You are an expert UI/UX researcher with access to user session data.
        Your goal is to answer the user's question based on the user session data.
        When the user mentions a question about users, they are asking about the user session data, so return the session ids.

        Total number of user sessions: {total_num_sessions}
        Today's date: {datetime.now().strftime("%Y-%m-%d")}

        You have access to the following tools:
        - filter_sessions: to search for relevant user sessions based on the query, don't input the query as is, but extract relevant information from the query and use it to filter the sessions.
 
        """

        react_agent = create_react_agent(
            self.gemini_llm, 
            [filter_sessions],
            prompt=system_prompt,
            response_format=Response
        )
        
        # Get the current messages from state
        messages = state["messages"]
        
        # Invoke the react agent with the messages and config
        response = react_agent.invoke(
            {"messages": messages},
            config=config
        )

        logger.info(f"Response: {response}")
        structured_response = response["structured_response"]
        
        # Return the updated messages
        return {"messages": response["messages"], "structured_response": structured_response}

    def get_graph(self) -> StateGraph:
        return self.graph

    @observe()  # type: ignore[misc]
    def discover(
        self, org_id: int, chat_id: int, messages: list[BaseMessage], total_num_sessions: int
    ) -> Dict[str, Any]:
        langfuse_context.update_current_trace(
            session_id=chat_id,
            user_id=org_id,
        )

        langfuse_handler = langfuse_context.get_current_langchain_handler()

        config = {
            "configurable": {
                # Checkpoints are accessed by thread_id
                "thread_id": chat_id,
                "org_id": org_id,
                "top_n": 15,
                "top_k": 30,
                "total_num_sessions": total_num_sessions,
            },
            "callbacks": [langfuse_handler],
        }
        
        # Create initial messages with the user query
        try:
            resp = self.graph.invoke(
                {"messages": [messages[-1]]},
                config=config,
                debug=False
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error", exc_info=e)
            raise e
