import os
import time
from typing import Any, Dict, List, Optional

from common.services.logger import logger
from common.schemas.session_analysis import SessionAnalysisResult
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


class State(TypedDict):
    recording_path: str
    recording_analysis: SessionAnalysisResult
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
            model="gemini-2.5-flash",
            # model="gemini-3-flash-preview",
            # model="gemini-3-pro-preview",
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
    ) -> SessionAnalysisResult:
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
                time.sleep(5)  # Adjust sleep time as needed
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
You are a highly skilled UX Analyst AI. Your task is to analyze a **video recording** of a user session and produce a **SessionAnalysisResult** object.

Your goal is to:
- Meticulously observe user actions in the recording
- Identify UX and technical issues
- Group the session into logical intervals
- Output a structured result matching the `SessionAnalysisResult` schema.

**Input:**
You will receive the video file and must reason about what is happening on the screen over time.

**Core Task:**

1.  **Analyze Sequentially:** Process the recording in chronological order.
2.  **Identify User Actions:** Determine what the user is doing at each moment (clicks, scrolling, typing, navigation, waiting, hesitation, etc.).
3.  **Observe System Responses:** Note how the system reacts (loading indicators, page changes, errors, success messages, visual feedback).
4.  **Extract Issues:** Identify any relevant **issues** from the recording:

    *   **Bugs:** Functionality not working as expected, errors, crashes.
    *   **Usability Issues:** Confusion, unclear labels, inefficient flows, difficulty finding information, design friction.
    *   **Performance Issues:** Noticeable delays in loading or responsiveness. Specifically flag delays **exceeding 3 seconds** as `PERFORMANCE_ISSUE`. Do not categorize normal user thinking/reading time as a performance issue.
    *   **Enhancements:** Opportunities to improve UX, simplify flows, or add helpful features, even if nothing explicitly "breaks".
5.  **Group into Intervals:** Group the session into logical sub-tasks or flows (e.g., logging in, filling a form, searching, completing checkout). Ensure intervals cover the session without gaps or overlaps.
6.  **Generate Structured Output:** Format your analysis **exactly** as a `SessionAnalysisResult` object.

**SessionAnalysisResult Schema:**

Top-level fields:

*   `title` (str, max 100 chars): Short title summarizing the main user task or session theme.
*   `summary` (str, max 200 chars): Concise summary of the user's journey, key actions, main issues/opportunities, and overall experience.
*   `health_score` (float 0–100): Higher = better experience. Penalize multiple or severe issues.
*   `confidence_score` (float 0–1): How confident you are in this analysis.
*   `user_actions` (List[str], max 8): Tags describing behavior and emotional state (e.g., hesitant, confused, frustrated, exploring, onboarding, purchasing, form_filling, browsing, searching, stuck, blocked).
*   `intervals` (List[TimestampInterval]): List of interval objects describing the whole session.

Each `TimestampInterval` MUST contain:

*   `start_time` (str, MM:SS): First timestamp in the interval.
*   `end_time`   (str, MM:SS): Last timestamp in the interval.
*   `short_title` (str): Short title summarizing the activity in this interval.
*   `issues` (List[Issue]): Issues that occur within this interval (can be empty).
*   `key_events` (List of objects): 3–5 of the most important events in this interval. Each object has `timestamp` (str, format MM:SS) and `description` (str, short human-readable description of what happened at that moment). Same structure as timestamp_descriptions.

Each `Issue` MUST contain:

*   `type`: `rage_click` | `dead_click` | `navigation_loop` | `form_struggle` | `scroll_thrashing` | `unknown`
*   `frequency` (int): How many repeated actions / occurrences (>= 1).
*   `timestamp` (str, MM:SS): When this issue first clearly appears.
*   `severity`: `low` | `medium` | `high` | `critical`
*   `confidence` (str | null): Your confidence in this issue detection: `high` | `medium` | `low`
*   `root_cause` (str): Your concise, technical hypothesis of WHY this happened, grounded in what is visible in the recording.
*   `reproduction_steps` (str): How an engineer could reliably reproduce this issue.
*   `target` (str | null): Element or URL involved (e.g., `"Reserve Your Spot" button` or `/checkout`).
*   `category`: `BUG` | `USABILITY_ISSUE` | `PERFORMANCE_ISSUE` | `ENHANCEMENT`

**Category Definitions & Rules:**

*   **BUG:** Use when functionality is broken, an error occurs, or the system prevents correct task completion.
*   **USABILITY_ISSUE:** Use when the user struggles, is confused, or faces friction due to design or workflow, even if the task eventually succeeds.
*   **PERFORMANCE_ISSUE:** Use *only* when there is clear visual indication of loading, processing, or unresponsiveness that lasts noticeably longer than 3 seconds.
*   **ENHANCEMENT:** Use when you see a meaningful opportunity to improve UX or add a valuable feature, even without a hard failure.

**Important Considerations:**

*   **Focus on Observation:** Base your analysis strictly on what is visible/audible in the recording. Infer intent/emotion cautiously from behavior (e.g., repeated clicks, backtracking, long pauses).
*   **Be Specific & Actionable:** Use concrete element names, timestamps, and behaviors so engineers can act on your output.
*   **Interval Logic:** Group the video into coherent sub-tasks that flow chronologically and cover the entire session.

Now, analyze the user session recording and return a **single JSON object** that strictly conforms to the `SessionAnalysisResult` model.

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
            response = self.gemini_llm.with_structured_output(
                SessionAnalysisResult
            ).invoke(messages)
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
