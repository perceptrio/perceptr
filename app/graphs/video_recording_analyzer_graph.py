import os
import time
from typing import Any, Dict, List, Optional

from common.services.logger import logger
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langfuse.decorators import langfuse_context, observe
from langgraph.graph import END, START, StateGraph
from settings import settings

from typing_extensions import TypedDict

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

import numpy as np
from google import genai
from pydantic import BaseModel, Field


class TimestampDescription(BaseModel):
    """A timestamp in the recording. Use the timestamp to describe the user's actions. Don't miss any timestamp."""
    description: str = Field(
        description="A detailed description of the user's actions, and what's happening on the screen."
    )
    timestamp: str = Field(description="The timestamp in the recording. Format: MM:SS")

class Finding(BaseModel): # Renamed from Insight
    """A finding identified from the recording."""
    description: str = Field(
        description="A detailed description of the finding." # Updated description
    )
    category: str = Field(
        description="The category of the finding. Can be one of: BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE, ENHANCEMENT" # Updated description
    )

class TimestampInterval(BaseModel):
    """A timestamp interval in the recording."""
    start_time: str = Field(
        description="The start time of the interval in the recording. Format: MM:SS"
    )
    end_time: str = Field(
        description="The end time of the interval in the recording. Format: MM:SS"
    )
    description: str = Field(
        description="A detailed description of the user's actions and system behavior within the interval." # Slightly refined description
    )
    findings: Optional[List[Finding]] = Field( # Renamed from insights, updated type hint
        default=None, # Explicitly default to None if preferred over implicit Optional behavior
        description="A list of findings identified during this interval. If there are no findings, leave it empty or null." # Updated description
    )
    short_title: str = Field(description="A short title summarizing the main activity or purpose of the interval.") # Slightly refined description
    timestamp_descriptions: List[TimestampDescription] = Field(
        description="A list of timestamp descriptions for every distinct timestamp/frame within the interval. Don't miss any." # Updated description
    )

class RecordingAnalysis(BaseModel):
    """The analysis of the user session recording, broken down into intervals.""" # Slightly refined description
    intervals: List[TimestampInterval] = Field(
        description="A list of logical intervals covering the entire recording." # Updated description
    )
    summary: str = Field(
        description="A concise summary of the user's overall journey, key actions, observed emotional state (if discernible), main findings (issues/opportunities), and actionable recommendations." # Updated description
    )
    title: str = Field(
        description="A title for the recording analysis, summarizing the main user task or overall session theme." # Updated description
    )


class State(TypedDict):
    recording_path: str
    recording_analysis: RecordingAnalysis
    file_type: str


class VideoRecordingAnalyzerGraph:
    def __init__(self) -> None:
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
            model="gemini-2.5-flash-preview-04-17",
            # model="gemini-2.0-flash",
            streaming=True,
            temperature=0,
        )
        # Configure genai client for file uploads
        # genai.configure(api_key=settings.GEMINI_API_KEY)
        self.gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

        graph_builder.add_node("recording_analyzer", self.recording_analyzer)

        graph_builder.add_edge(START, "recording_analyzer")
        graph_builder.add_edge("recording_analyzer", END)

        self.graph = graph_builder.compile()


    def gemini_recording_analyzer(
        self, recording_path: str, file_type: str
    ) -> RecordingAnalysis:
        # --- Upload video using File API ---
        logger.info(f"Uploading video file: {recording_path} using File API...")
        # Consider adding error handling for file not found
        try:
            uploaded_file = self.gemini_client.files.upload(
                file=recording_path,
                config={
                    "mime_type": file_type,
                },
            )
            logger.info(
                f"File uploaded successfully",
                file_uri=uploaded_file.uri,
                file_name=uploaded_file.name,
            )

            # Wait for the file to be processed
            while uploaded_file.state.name == "PROCESSING":
                logger.info(
                    "Waiting for video processing...",
                    file_uri=uploaded_file.uri,
                    file_name=uploaded_file.name,
                )
                time.sleep(10)  # Adjust sleep time as needed
                # Fetch the latest file state
                uploaded_file = self.gemini_client.files.get(name=uploaded_file.name)

            if uploaded_file.state.name == "FAILED":
                logger.error(
                    f"Video file processing failed",
                    file_uri=uploaded_file.uri,
                    file_name=uploaded_file.name,
                )
                raise ValueError(
                    f"Video processing failed for file: {uploaded_file.name}"
                )

            logger.info(
                "Video file ready",
                file_uri=uploaded_file.uri,
                file_name=uploaded_file.name,
            )

            # Ensure correct mime_type is used - get it from the uploaded file object
            mime_type = uploaded_file.mime_type
            file_uri = uploaded_file.uri

        except Exception as e:
            logger.error(
                "Error during video upload or processing",
                exc_info=e,
                file_uri=uploaded_file.uri,
                file_name=uploaded_file.name,
            )
            # Consider how to handle this - maybe raise a specific exception
            # For now, re-raising the original exception
            raise e
        # --- End File API Upload ---

        # Create the prompt.
        prompt = """
You are a highly skilled UX Analyst AI. Your task is to analyze video recordings of user sessions provided as a sequence of timestamped frames or descriptions. Your goal is to meticulously observe user actions, identify any **findings** (bugs, usability problems, performance lags, potential enhancements), and evaluate the UI design at each step.

**Input:**
You will receive data representing a user session recording, likely as a series of screenshots or frames, each associated with a timestamp (e.g., MM:SS).

**Core Task:**

1.  **Analyze Sequentially:** Process the timestamps in chronological order.
2.  **Identify User Actions:** Determine what the user is doing at each timestamp (e.g., clicking a button, scrolling, typing text, navigating between pages, waiting, hesitating).
3.  **Observe System Responses:** Note how the system reacts (e.g., loading indicators, page changes, error messages, successful operations, visual feedback).
4.  **Extract Findings:** Identify any relevant **findings** from the recording:

    *   **Bugs:** Functionality not working as expected, errors, crashes.
    *   **Usability Issues:** Points of confusion, unexpected behavior, inefficient workflows, difficulty finding information, unclear labels/instructions, design friction.
    *   **Performance Issues:** Noticeable delays in loading or responsiveness. Specifically flag delays **exceeding 3 seconds** as `PERFORMANCE_ISSUE`. Do not categorize normal user thinking/reading time as a performance issue.
    *   **Enhancements:** Observe situations where a feature could be improved or a new feature could significantly help the user's workflow, even if no explicit issue occurred. Think about opportunities for simplification, efficiency gains, or better user guidance.
5.  **Group into Intervals:** Group consecutive timestamps that represent a single, logical user sub-task or interaction flow (e.g., logging in, filling out a form section, attempting a search, completing a purchase step). Ensure intervals cover the entire session duration without gaps or overlaps in time.
6.  **Generate Structured Output:** Format your analysis precisely according to the Pydantic models provided (`RecordingAnalysis`, `TimestampInterval`, `Finding`, `TimestampDescription`).

**Output Structure:**

Generate a single `RecordingAnalysis` JSON object containing:

*   `title`: A title for the recording analysis, summarizing the main user task or overall session theme.
*   `summary`: A concise summary of the user's overall journey, key actions, observed emotional state (if discernible), main findings (issues/opportunities), and actionable recommendations.
*   `intervals`: A list of `TimestampInterval` objects. Each interval object must contain:
    *   `start_time`: The first timestamp (MM:SS) in the interval.
    *   `end_time`: The last timestamp (MM:SS) in the interval.
    *   `short_title`: A short title summarizing the main activity or purpose of the interval.
    *   `description`: A clear, narrative description of the user's actions and system behavior during this specific interval.
    *   `findings`: A list of `Finding` objects identified within this interval (or null/empty list if none). Each `Finding` object includes:
        *   `description`: A detailed description of the specific finding.
        *   `category`: Classify the **finding** as one of: `BUG`, `USABILITY_ISSUE`, `PERFORMANCE_ISSUE`, `ENHANCEMENT`.
    *   `timestamp_descriptions`: A list of `TimestampDescription` objects, one for each distinct timestamp/frame provided within this interval. Each includes:
        *   `timestamp`: The specific timestamp (MM:SS).
        *   `description`: A detailed description of user actions and screen state *at that specific timestamp*.

**Category Definitions & Rules:**

*   **BUG:** Use when functionality is broken, an error occurs (system error, validation error preventing progress inappropriately), or the system behaves in a way that prevents task completion correctly. High impact, requires fixing.
*   **USABILITY_ISSUE:** Use when the user struggles, seems confused, hesitates, takes inefficient paths, expresses frustration (if discernible), or encounters friction due to the design or workflow. The core functionality might still work, but the experience is suboptimal.
*   **PERFORMANCE_ISSUE:** Use *only* when there is a clear visual indication of loading, processing, or unresponsiveness that lasts noticeably longer than 3 seconds. Requires visual evidence (e.g., spinner, frozen screen). Do *not* use for normal user thinking/reading time between interactions.
*   **ENHANCEMENT:** Use when you identify an opportunity to improve the existing UI/UX or suggest a new feature based on the user's interaction or workflow, even if no explicit "issue" occurred. This focuses on making tasks easier, faster, clearer, or more delightful.

**Important Considerations:**

*   **Focus on Observation:** Base your analysis strictly on what is visible/audible in the recording. Infer user intent and emotion cautiously based *only* on their actions and behaviors (e.g., repeated clicks, backtracking, long pauses before action).
*   **Be Specific & Actionable:** Descriptions for intervals, findings, and timestamps should be clear, detailed, and provide enough context to be understood and potentially acted upon. Avoid vague language.
*   **Interval Logic:** Group timestamps logically based on the user attempting and completing (or abandoning) a coherent sub-task. Intervals should flow chronologically and cover the entire session.
*   **Timestamp Granularity:** Ensure every timestamp provided in the input is accounted for within exactly one `TimestampDescription` inside its corresponding `TimestampInterval`.

Now, please analyze the provided user session recording data and generate the structured JSON output conforming to the `RecordingAnalysis` model.

                    """

        # Construct message using file_uri from File API
        messages = [
            HumanMessage(
                content=[
                    {
                        "type": "media",
                        "mime_type": mime_type,
                        "file_uri": file_uri,  # Use file_uri instead of data
                    },
                    {"type": "text", "text": prompt},
                ]
            )
        ]
        try:
            response = self.gemini_llm.with_structured_output(RecordingAnalysis).invoke(
                messages
            )
        finally:
            # Clean up the uploaded file on Google Cloud Storage
            # Optional: Keep if you might reuse the file quickly, but generally good to clean up.
            try:
                logger.info(f"Deleting uploaded file", file_uri=uploaded_file.uri)
                self.gemini_client.files.delete(name=uploaded_file.name)
            except Exception as delete_error:
                logger.warning(
                    f"Failed to delete uploaded file",
                    file_uri=uploaded_file.uri,
                    file_name=uploaded_file.name,
                    exc_info=delete_error,
                )

        return response

    def recording_analyzer(self, state: State, config: RunnableConfig) -> dict:
        recording_path = state["recording_path"]
        file_type = state["file_type"]
        response = self.gemini_recording_analyzer(recording_path, file_type)

        return {
            "recording_path": recording_path,
            "file_type": file_type,
            "recording_analysis": response,
        }

    def get_graph(self) -> StateGraph:
        return self.graph

    @observe()  # type: ignore[misc]
    def analyze_recording(
        self,
        org_id: str,
        recording_id: str,
        recording_path: str,
        file_type: str,
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
                "llm": "OPENAI",
            },
            "callbacks": [langfuse_handler],
        }
        try:
            resp = self.graph.invoke(
                {"recording_path": recording_path, "file_type": file_type},
                config=config,
                # debug=True
            )
            return resp
        except Exception as e:
            logger.error(f"Error creating graph with response error", exc_info=e)
            raise e
