import os
import time
from typing import Any, Dict

from common.services.logger import logger
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langfuse.decorators import langfuse_context, observe
from langgraph.graph import END, START, StateGraph
from settings import settings
from typing_extensions import TypedDict

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
from pydantic import BaseModel, Field


class RecordingSummary(BaseModel):
    summary: str = Field(
        description="A summary of the user's actions, behavior, emotional state. Also include any issues found in the recording and recommendations for improvement. The summary should be in the form of a story of the user's experience, from beginning to end."
    )
    short_title: str = Field(
        description="A short title for the recording. It should be a single sentence that captures the main idea of the recording."
    )


class State(TypedDict):
    recording_summary: RecordingSummary
    recording_intervals_summary: str


class RecordingSummarizerGraph:
    def __init__(self) -> None:
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o",
            streaming=True,
            temperature=0,
        )
        graph_builder.add_node("recording_summarizer", self.recording_summarizer)
        graph_builder.add_edge(START, "recording_summarizer")
        graph_builder.add_edge("recording_summarizer", END)
        self.graph = graph_builder.compile()

    def recording_summarizer(self, state: State, config: RunnableConfig) -> dict:
        recording_intervals_summary = state["recording_intervals_summary"]

        prompt = """You are an expert UI/UX Researcher analyzing a user session.
        You are given a summary of the user's actions, behavior, and emotional state of a recording intervals.

        You are to summarize the recording intervals into a short title and a summary of the user's actions, behavior, and emotional state.
                    """

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=recording_intervals_summary),
        ]

        response = self.openai_llm.with_structured_output(RecordingSummary).invoke(
            messages
        )

        return {"recording_summary": response}

    def get_graph(self) -> StateGraph:
        return self.graph

    @observe()  # type: ignore[misc]
    def summarize_recording(
        self, org_id: str, recording_id: str, recording_intervals_summary: str
    ) -> Dict[str, Any]:
        langfuse_context.update_current_trace(
            session_id=recording_id,
            user_id=org_id,
        )

        langfuse_handler = langfuse_context.get_current_langchain_handler()

        config = {
            "configurable": {
                # Checkpoints are accessed by thread_id
                "thread_id": recording_id,
            },
            "callbacks": [langfuse_handler],
        }
        try:
            resp = self.graph.invoke(
                {"recording_intervals_summary": recording_intervals_summary},
                config=config,
                # debug=True
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error: {str(e)}")
            raise e
