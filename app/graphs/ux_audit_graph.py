import os
import time
from typing import Any, Dict, List

from common.services.logger import logger
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langfuse.decorators import langfuse_context, observe
from langgraph.graph import END, START, StateGraph
from settings import settings
from typing_extensions import TypedDict
from langchain_google_genai import ChatGoogleGenerativeAI
import base64

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST
from pydantic import BaseModel, Field


class Issue(BaseModel):
    issue_title: str = Field(
        description="A title of the issue found in the screen."
    )
    issue: str = Field(
        description="A detailed description of the issue found in the screen."
    )
    recommendation: str = Field(
        description="A detailed recommendation for improvement."
    )

class UXAudit(BaseModel):
    short_title: str = Field(
        description="A short title for the screen. It should be a single sentence that captures the main idea of the screen."
    )

    summary: str = Field(
        description="A summary of the UX audit of the screen."
    )

    issues: List[Issue] = Field(
        description="A list of issues found in the screen."
    )
    


class State(TypedDict):
    ux_audit_report: str
    frame_path: str


class UXAuditGraph:
    def __init__(self) -> None:
        graph_builder = StateGraph(State)
        self.gemini_llm = ChatGoogleGenerativeAI(
            api_key=settings.GEMINI_API_KEY,
            # model="gemini-2.5-pro-preview-05-06",
            model="gemini-2.5-flash",
            temperature=0,
        )
        graph_builder.add_node("ux_audit", self.ux_audit)
        graph_builder.add_edge(START, "ux_audit")
        graph_builder.add_edge("ux_audit", END)
        self.graph = graph_builder.compile()

    def ux_audit(self, state: State, config: RunnableConfig) -> dict:
        frame_path = state["frame_path"]



        prompt = """You are an expert UI/UX Auditor.
        You are given a screen of a web application, or a mobile app, or a desktop app.
        You are to audit the UX of the screen and provide a summary of the UX.
        You are to provide a list of issues and recommendations for improvement.
        You are to provide a short title for the screen.
        """

        with open(frame_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

        message = HumanMessage(
    content=[
        {"type": "text", "text": "Audit the UX of the screen:"},
        {"type": "image_url", "image_url": f"data:image/png;base64,{encoded_string}"},
    ],
)

        messages = [
            SystemMessage(content=prompt),
            message,
        ]

        response = self.gemini_llm.with_structured_output(UXAudit).invoke(
            messages
        )


        return {"ux_audit_report": response}


    @observe()  # type: ignore[misc]
    def audit_ux(
        self, user_email: str, frame_timestamp: str, frame_path: str
    ) -> Dict[str, Any]:
        langfuse_context.update_current_trace(
            session_id=frame_timestamp,
            user_id=user_email,
        )

        langfuse_handler = langfuse_context.get_current_langchain_handler()

        config = {
            "configurable": {
                # Checkpoints are accessed by thread_id
                "thread_id": user_email,
            },
            "callbacks": [langfuse_handler],
        }
        try:
            resp = self.graph.invoke(
                {"frame_path": frame_path},
                config=config,
                # debug=True
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error", exc_info=e)
            raise e
