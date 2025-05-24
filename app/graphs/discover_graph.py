import os
from typing import Any, Dict, List, Annotated

from common.services.logger import logger
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AnyMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse.decorators import langfuse_context, observe
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from settings import settings
from typing_extensions import TypedDict
from tools.discover_tools import filter_sessions

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


class DiscoverGraph:
    def __init__(self) -> None:
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4.1-mini",
            streaming=True,
            temperature=0,
        )
        
        graph_builder.add_node("discover_node", self.discover_node)
        graph_builder.add_edge(START, "discover_node")
        graph_builder.add_edge("discover_node", END)
        self.graph = graph_builder.compile()

    def discover_node(self, state: State, config: RunnableConfig) -> dict:
        # Create react agent with filter_sessions tool
        react_agent = create_react_agent(
            self.openai_llm, 
            [filter_sessions],
            prompt="You are an expert UI/UX researcher with access to user session data. Use the filter_sessions tool to search for relevant user sessions based on the query, then provide a comprehensive analysis and answer based on the retrieved session data."
        )
        
        # Get the current messages from state
        messages = state["messages"]
        
        # Invoke the react agent with the messages and config
        response = react_agent.invoke(
            {"messages": messages},
            config=config
        )
        
        # Return the updated messages
        return {"messages": response["messages"]}

    def get_graph(self) -> StateGraph:
        return self.graph

    @observe()  # type: ignore[misc]
    def discover(
        self, org_id: int, chat_id: int, query: str
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
                "top_n": 5,
                "top_k": 30,
            },
            "callbacks": [langfuse_handler],
        }
        
        # Create initial messages with the user query
        initial_messages = [HumanMessage(content=query)]
        
        try:
            resp = self.graph.invoke(
                {"messages": initial_messages},
                config=config,
                debug=True
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error", exc_info=e)
            raise e
