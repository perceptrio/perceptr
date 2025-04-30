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

# from pydantic import BaseModel, Field
from typing_extensions import TypedDict

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

import numpy as np
from google import genai
from pydantic import BaseModel, Field
from utils.graph import map_timestamped_frames_to_messages


class TimestampDescription(BaseModel):
    """A timestamp in the recording. Use the timestamp to describe the user's actions. Don't miss any timestamp."""

    description: str = Field(
        description="A detailed description of the user's actions, and what's happening on the screen."
    )
    ui_design_feedback: Optional[str] = Field(
        description="Observations and recommendations focused solely on the UI elements and overall visual design of the screenshot. Assess aspects such as layout, alignment, color contrast, typography, spacing, and responsiveness. Note any areas where the design could be optimized, improved, or clarified. If no visual feedback is required, leave this field empty. No need for positive feedback, only feedback on what could be improved."
    )
    timestamp: str = Field(description="The timestamp in the recording. Format: MM:SS")


# class RecordingAnalysis(BaseModel):
#     """The analysis of the recording."""
#     timestamp_descriptions: List[TimestampDescription] = Field(description="A list of timestamp descriptions.")
#     summary: str = Field(description="A summary of the user's behavior, emotional state, and recommendations for improvement.")


class TimestampInterval(BaseModel):
    """A timestamp interval in the recording."""

    start_time: str = Field(
        description="The start time of the interval in the recording. Format: MM:SS"
    )
    end_time: str = Field(
        description="The end time of the interval in the recording. Format: MM:SS"
    )
    description: str = Field(
        description="A detailed description of the user's actions in the interval."
    )
    issue: Optional[str] = Field(
        description="The issue found in the interval. If there is no issue, leave it empty."
    )
    category: str = Field(
        description="The category of the interval. Can be one of: NORMAL, BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE, ENHANCEMENT"
    )
    short_title: str = Field(description="A short title for the interval.")
    timestamp_descriptions: List[TimestampDescription] = Field(
        description="A list of timestamp description in the interval. Don't miss any timestamp."
    )


class RecordingAnalysis(BaseModel):
    """The intervals of the recording."""

    intervals: List[TimestampInterval] = Field(
        description="The intervals of the recording."
    )
    summary: str = Field(
        description="A summary of the user's actions, behavior, emotional state. Also include any issues found in the recording and recommendations for improvement."
    )
    title: str = Field(
        description="A title for the recording. It should be a short description of the user's actions, behavior, emotional state."
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
            # model="gemini-2.5-pro-exp-03-25",
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

    # def gemini_recording_analyzer(self, recording_path: str):
    #     logger.info("Uploading file...")
    #     uploaded_recording = genai.upload_file(path=recording_path)
    #     logger.info(f"Completed upload: {uploaded_recording.uri}")

    #     # Check whether the file is ready to be used.
    #     while uploaded_recording.state.name == "PROCESSING":
    #         print('.', end='')
    #         time.sleep(5)
    #         uploaded_recording = genai.get_file(uploaded_recording.name)

    #     if uploaded_recording.state.name == "FAILED":
    #         raise ValueError(uploaded_recording.state.name)

    #     logger.info(f"File ready: {uploaded_recording.uri}")

    #     # Create the prompt.
    #     prompt =  """You are an expert UI/UX Researcher analyzing a user session.
    #     For each timestamp in the recording, provide a detailed analysis of the user's behavior and emotional state.

    #      Focus on:
    #                 1. Signs of user frustration (rapid movements, rage clicks)
    #                 2. Navigation patterns and hesitation points
    #                 3. Areas where the user seems confused or stuck
    #                 4. Interaction with specific UI elements
    #                 5. Bugs and issues
    #                 6. Errors and issues

    #     Then at the end, provide a summary of the user's behavior, emotional state, and recommendations for improvement.

    #                 """

    #     messages = [
    #         HumanMessage(content=[{
    #         "type": "media",
    #         "mime_type": uploaded_recording.mime_type,
    #         "file_uri": uploaded_recording.uri
    #     },]),
    #         HumanMessage(content=prompt)
    #     ]

    #     response = self.gemini_llm.with_structured_output(RecordingAnalysis).invoke(messages)

    #     return response

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
You are a highly skilled UX Analyst AI. Your task is to analyze video recordings of user sessions provided as a sequence of timestamped frames or descriptions. Your goal is to meticulously observe user actions, identify any issues (bugs, usability problems, performance lags, potential enhancements), and evaluate the UI design at each step.

**Input:**
You will receive data representing a user session recording, likely as a series of screenshots or frames, each associated with a timestamp.

**Core Task:**
1.  **Analyze Sequentially:** Process the timestamps in chronological order.
2.  **Identify User Actions:** Determine what the user is doing at each timestamp (e.g., clicking a button, scrolling, typing text, navigating between pages, waiting).
3.  **Observe System Responses:** Note how the system reacts (e.g., loading indicators, page changes, error messages, successful operations).
4.  **Detect Issues:** Identify any problems the user encounters or that are apparent from the recording:
    *   **Bugs:** Functionality not working as expected, errors, crashes.
    *   **Usability Issues:** Points of confusion, unexpected behavior, inefficient workflows, difficulty finding information, unclear labels/instructions.
    *   **Performance Issues:** Noticeable delays in loading or responsiveness. Specifically flag delays **exceeding 3 seconds** as `PERFORMANCE_ISSUE`.
    *   **Enhancements:** Observe situations where a feature could be improved or a new feature could significantly help the user's workflow, even if no explicit issue occurred.
5.  **Evaluate UI Design:** At each timestamp, critically assess the visual presentation (layout, spacing, alignment, contrast, typography, visual hierarchy, clarity of elements). Focus *only* on constructive feedback for improvement.
6.  **Group into Intervals:** Group consecutive timestamps that represent a single, logical user sub-task or interaction flow (e.g., logging in, filling out a form section, attempting a search).
7.  **Generate Structured Output:** For each logical interval identified, format your analysis precisely according to the structure below.

**Output Structure:**

Provide your analysis as a list of interval objects. Each interval object must contain the following fields:

- **Start Time:** The first timestamp in the group.
- **End Time:** The last timestamp in the group.
- **Detailed Description:** A clear description of the user's actions and observations during the interval.
- **Issue:** If an issue is detected, provide a detailed description of the issue. If no issue is detected, leave it empty.
- **Category:** Classify the interval as one of the following:
  - **BUG:** Issues that significantly impact functionality and need immediate resolution.
  - **USABILITY_ISSUE:** Problems that hinder user experience but do not completely break functionality.
  - **PERFORMANCE_ISSUE:** Concerns related to speed, load times, or responsiveness. Only mark as performance issue if the loading time is more than 3 seconds.
  - **ENHANCEMENT:** Suggestions for improvements or new features to enhance the user experience.
  - **NORMAL:** Routine user actions without any apparent issues.
  *Note: If any issue is detected, it should override the NORMAL categorization.*
- **Short Title:** A short title for the interval.
- **Timestamp Descriptions:** A list of timestamp descriptions for every timestamp included in the interval. Contains the following fields:
    - **Description:** A detailed description of the user's actions and observations during the interval.
    - **UI Design Feedback:** Observations and recommendations focused solely on the UI elements and overall visual design of the screenshot. Assess aspects such as layout, alignment, color contrast, typography, spacing, and responsiveness. Note any areas where the design could be optimized, improved, or clarified. If no visual feedback is required, leave this field empty. No need for positive feedback, only feedback on what could be improved.
    - **Timestamp:** The timestamp in the recording. Format: MM:SS



**Category Definitions & Rules:**

- **BUG:** Use when functionality is broken, an error occurs, or the system behaves in a way that prevents task completion correctly. High impact.

- **USABILITY_ISSUE:** Use when the user struggles, seems confused, takes inefficient paths, or encounters friction due to the design or workflow, but the core functionality might still work (perhaps with difficulty).

- **PERFORMANCE_ISSUE:** Use only when there is a clear visual indication of loading or unresponsiveness that lasts longer than 3 seconds. Do not use for normal user thinking time.

- **ENHANCEMENT:** Use when you identify an opportunity to improve the existing UI/UX or suggest a new feature based on the user's interaction, even if no explicit "issue" occurred. This often relates to making tasks easier or more efficient.

- **NORMAL:** Use only when the user performs routine actions smoothly without any detectable issues or clear enhancement opportunities within the interval.

**Override Rule:** If any issue (BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE) is detected within an interval, the category cannot be NORMAL. If an ENHANCEMENT is suggested but no specific issue is present, use ENHANCEMENT, not NORMAL. Prioritize BUG > USABILITY_ISSUE > PERFORMANCE_ISSUE > ENHANCEMENT > NORMAL.


**Important Considerations:**

- Focus on Observation: Base your analysis strictly on what is visible in the recording. Infer user intent cautiously based on their actions.

- Be Specific: Descriptions and issue details should be clear and actionable. Avoid vague language.

- UI Feedback Focus: Remember, UI Design Feedback is only about visual design elements and layout improvements. Functional issues go into the main Issue field. Do not provide positive UI feedback, only constructive criticism.

- Interval Logic: Group timestamps logically based on the user completing a small, coherent part of their overall task. Intervals can vary in duration.

- Timestamp Granularity: Ensure each entry in Timestamp Descriptions corresponds to a distinct moment/frame provided in the input.

Now, please analyze the provided user session recording data and generate the structured output as defined above.

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
