import os
import time
from typing import Any, Dict, List, Union

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


class NewIssue(BaseModel):
    issue_title: str = Field(description="The title of the issue.")
    issue_description: str = Field(description="A description of the issue.")
    issue_recommendation: str = Field(
        description="A recommendation on how to fix/enhance the issue."
    )
    issue_severity: str = Field(
        description="The severity of the issue. It should be one of the following: LOW, MEDIUM, HIGH"
    )
    issue_category: str = Field(
        description="The category of the issue. It should be one of the following: BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE, ENHANCEMENT"
    )


class ExistingIssue(BaseModel):
    issue_id: int = Field(description="The id of the issue.")


class Issue(BaseModel):
    recording_interval_id: int = Field(
        description="The id of the recording interval that the issue belongs to."
    )
    is_new_issue: bool = Field(
        description="Whether the issue is new or not. If it is a new issue, it should be True, otherwise it should be False."
    )
    issue: Union[NewIssue, ExistingIssue] = Field(
        description="The issue found in the recording interval. If it is a new issue, it should be a NewIssue object, otherwise it should be an ExistingIssue object."
    )


class Issues(BaseModel):
    issues: list[Issue] = Field(description="A list of issues found in the recording.")


class State(TypedDict):
    analyzed_recording_issues: list[dict]
    existing_issues: list[dict]
    aggregated_issues: Issues


class IssuesSummarizerGraph:
    def __init__(self) -> None:
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4.1-mini",
            streaming=True,
            temperature=0,
        )
        graph_builder.add_node("issues_summarizer", self.issues_summarizer)
        graph_builder.add_edge(START, "issues_summarizer")
        graph_builder.add_edge("issues_summarizer", END)
        self.graph = graph_builder.compile()

    def issues_summarizer(self, state: State, config: RunnableConfig) -> dict:
        prompt = """You are a UI/UX Researcher analyzing a user session.
        You will be given two lists of issues.
        The first list is a list of issues that were found in the recording.
        The second list is a total list of issues that have been found in the past.

        Your task is to analyze the issues in the recording and determine if any of them are new or if they have been reported before.

        To determine if an issue has been reported before, you should check if the issue description is semantically similar to any of the issues in the past.
        Even if the issue description is not exactly the same, if the issue is related to the same problem, you should consider it as a duplicate.

        If the issue has been reported before, you should return the issue id.
        If the issue has not been reported before, you should return a new issue object.

        The issue object should contain the following fields:
        - issue_description: A description of the issue.
        - issue_recommendation: A recommendation on how to fix/enhance the issue.
        - issue_severity: The severity of the issue. Can be LOW, MEDIUM, HIGH.
        - issue_category: The category of the issue. Can be BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE, ENHANCEMENT.
        """

        human_message = f"""
        Here are the existing issues:
        {state["existing_issues"]}

        Here are the issues found in the recording:
        {state["analyzed_recording_issues"]}
        """

        messages = [SystemMessage(content=prompt), HumanMessage(content=human_message)]

        response = self.openai_llm.with_structured_output(Issues).invoke(messages)

        return {"aggregated_issues": response}

    def get_graph(self) -> StateGraph:
        return self.graph

    @observe()  # type: ignore[misc]
    def aggregate_issues(
        self,
        org_id: str,
        recording_id: str,
        analyzed_recording_issues: List[dict],
        existing_issues: List[dict],
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
                {
                    "analyzed_recording_issues": analyzed_recording_issues,
                    "existing_issues": existing_issues,
                },
                config=config,
                # debug=True
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error", exc_info=e)
            raise e
