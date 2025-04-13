import os
import time
from typing import Annotated, Any, Dict, List, Optional, Tuple

from common.services.logger import logger
from langchain_core.messages import HumanMessage, SystemMessage
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
    timestamp: str = Field(
        description="The timestamp in the recording. Format: HH:MM:SS"
    )


# class RecordingAnalysis(BaseModel):
#     """The analysis of the recording."""
#     timestamp_descriptions: List[TimestampDescription] = Field(description="A list of timestamp descriptions.")
#     summary: str = Field(description="A summary of the user's behavior, emotional state, and recommendations for improvement.")


class TimestampInterval(BaseModel):
    """A timestamp interval in the recording."""

    start_time: str = Field(
        description="The start time of the interval in the recording. Format: HH:MM:SS"
    )
    end_time: str = Field(
        description="The end time of the interval in the recording. Format: HH:MM:SS"
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


class State(TypedDict):
    timestamped_frames: List[Tuple[str, np.ndarray, str]]
    recording_analysis: RecordingAnalysis


class RecordingAnalyzerGraph:
    def __init__(self) -> None:
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o",
            streaming=True,
            temperature=0,
        )
        self.gemini_llm = ChatGoogleGenerativeAI(
            api_key=settings.GEMINI_API_KEY,
            # model="gemini-2.5-pro-exp-03-25",
            model="gemini-2.0-flash",
            streaming=True,
            temperature=0,
        )

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

    def openai_recording_analyzer(
        self, timestamped_frames: List[Tuple[str, np.ndarray, str]]
    ) -> RecordingAnalysis:
        # Create the prompt.
        prompt = """
You are an expert UI/UX Researcher analyzing a user session. You are given a list of timestamps along with an image of the user's screen at each timestamp and an RRWeb summary of the event at each timestamp. Your task is to analyze the recording and provide a detailed, grouped, timestamped analysis of the user's actions, behavior, and any UI issues observed. **Group consecutive timestamps that represent similar or related actions into a single interval.** Each interval should capture a single action or a set of related actions.

**For each interval, include:**
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
    - **Timestamp:** The timestamp in the recording. Format: HH:MM:SS


**Focus Areas:**
1. **User Behavior & Interaction:**
   - Identify signs of user frustration (e.g., rapid or repeated clicks, hesitations, or abrupt movements).
   - Examine navigation patterns, particularly moments of hesitation or repeated attempts.
   - Highlight any moments where the user appears confused or stuck.

2. **Interaction with UI Elements:**
   - Assess how users interact with buttons, menus, forms, and other interactive elements.
   - Detect if UI elements (e.g., buttons, links, icons) are unresponsive, misplaced, or unclear.
   - Note if tooltips, modals, or error messages appear and whether they aid or confuse the user.

3. **Layout & Visual Design:**
   - Evaluate the consistency of the layout, including alignment, spacing, and visual hierarchy.
   - Look for issues with readability, such as poor contrast between text and background.
   - Identify visual clutter, overlapping elements, or design elements that might cause confusion.

4. **Accessibility:**
   - Check if UI elements are accessible (e.g., adequate size for click/tap, keyboard navigation support).
   - Assess whether error messages and labels are clear and assistive.
   - Note any potential barriers for users with visual or motor impairments.

5. **Performance & Responsiveness:**
   - Observe any lag, slow load times, or sudden reflows of the UI.
   - Identify any elements that are unresponsive or cause delays in the user's workflow.

6. **Error Handling & Feedback:**
   - Document any bugs or errors that occur and how the UI communicates them.
   - Note if error messages or feedback mechanisms are helpful and clear.

7. **Opportunities for Enhancement:**
   - Suggest improvements for usability and overall design.
   - Recommend new features or refinements that could streamline user interactions.
   - Provide actionable insights to improve the user experience (e.g., "Increase button size for better touch targets," "Improve color contrast for readability").

**Instructions:**

- **Grouping:**
  - **Group consecutive timestamps** that reflect a single action or a set of related actions into one interval.
  - If a timestamp clearly represents a distinct action not related to its neighbors, it should start a new interval.

- **Comprehensiveness:**
  - Ensure that every provided timestamp is included in the analysis either as its own interval or as part of a grouped interval.
  - Provide both macro-level (overall session behavior) and micro-level (detailed UI element interactions) insights.

- **Clarity:**
  - Use clear, concise language. Reference specific timestamps, UI elements, and user behaviors.

- **Actionable Insights:**
  - Provide concrete recommendations for each identified issue, prioritizing bugs and usability issues over normal interactions.

- **Final Check:**
  - Before finalizing your analysis, verify that every provided timestamp is included in the output and appropriately grouped into intervals based on similarity of actions.

                    """

        messages = [
            SystemMessage(content=prompt),
            *map_timestamped_frames_to_messages(timestamped_frames),
        ]

        response = self.gemini_llm.with_structured_output(RecordingAnalysis).invoke(
            messages
        )
        return response  # type: ignore[no-any-return]

    def recording_analyzer(self, state: State, config: RunnableConfig) -> dict:
        timestamped_frames = state["timestamped_frames"]
        response = self.openai_recording_analyzer(timestamped_frames)

        return {"recording_analysis": response}

    # def extract_timestamped_intervals(self, state: State) -> dict:
    #     recording_analysis = state["recording_analysis"]

    #     prompt = """
    #     You are an expert UI/UX Researcher analyzing a user session.

    #     You are given a list of timestamps along with a description of the user's actions at each timestamp.

    #     Your task is to group the timestamps into intervals based on the user's actions.

    #     Each interval should be a single action or a set of actions that are related to each other.

    #     The intervals should be grouped into categories based on the user's actions.

    #     The categories are:

    #     NORMAL: The user is performing their normal actions.

    #     BUG: Issues that significantly impact functionality and need immediate resolution.

    #     USABILITY_ISSUE: Problems that hinder user experience but don't necessarily break functionality.

    #     PERFORMANCE_ISSUE: Concerns related to speed, load times, or responsiveness.

    #     ENHANCEMENT: Suggestions for improvements or new features that could enhance user experience.

    #     If any issue is found, it takes priority over the NORMAL category.
    #                 """

    #     messages = [
    #         SystemMessage(content=prompt),
    #         HumanMessage(content=recording_analysis.json())
    #     ]

    #     response = self.openai_llm.with_structured_output(RecordingIntervals).invoke(messages)

    #     return {
    #         "recording_intervals": response
    #     }

    def get_graph(self) -> StateGraph:
        return self.graph

    @observe()  # type: ignore[misc]
    def analyze_recording(
        self,
        org_id: str,
        recording_id: str,
        timestamped_frames: List[Tuple[str, np.ndarray, str]],
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
                {"timestamped_frames": timestamped_frames},
                config=config,
                # debug=True
            )
            return resp  # type: ignore[no-any-return]
        except Exception as e:
            logger.error(f"Error creating graph with response error: {str(e)}")
            raise e
