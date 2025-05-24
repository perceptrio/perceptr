import os
from typing import Any, Dict, List, Annotated
from datetime import datetime
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

        total_num_sessions = config.get("configurable", {}).get("total_num_sessions")

        system_prompt = f"""
        You are an expert UI/UX researcher with access to user session data.
        Your goal is to answer the user's question based on the user session data.

        Total number of user sessions: {total_num_sessions}
        Today's date: {datetime.now().strftime("%Y-%m-%d")}

        You have access to the following tools:
        - filter_sessions: to search for relevant user sessions based on the query, don't input the query as is, but extract relevant information from the query and use it to filter the sessions.
 
        """

        react_agent = create_react_agent(
            self.openai_llm, 
            [filter_sessions],
            prompt=system_prompt
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
                "top_k": total_num_sessions,
                "total_num_sessions": total_num_sessions,
            },
            "callbacks": [langfuse_handler],
        }
        
        # Create initial messages with the user query
        try:
            resp = self.graph.invoke(
                {"messages": messages},
                config=config,
                debug=True
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error", exc_info=e)
            raise e
