from typing import Annotated

# from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from settings import settings
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage
from langfuse.decorators import langfuse_context, observe
from common.services.logger import logger
import os
import time

os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import Optional, List, Tuple, Dict
import json
from utils.rrweb import DecimalEncoder



class TimestampDescription(BaseModel):
    """A timestamp in the recording. Use the timestamp to describe the user's actions. Don't miss any timestamp."""

    description: str = Field(
        description="A detailed description of the user's actions, and what's happening on the screen."
    )

    timestamp: str = Field(
        description="The timestamp in the recording. Format: HH:MM:SS"
    )



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
    events: List[Dict]
    recording_analysis: RecordingAnalysis


class RRWEBRecordingAnalyzerGraph:
    def __init__(self):
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(
            api_key=settings.OPENAI_API_KEY,
            model="gpt-4o",
            streaming=True,
            temperature=0,
        )

        genai.configure(api_key=settings.GEMINI_API_KEY)

        graph_builder.add_node("recording_analyzer", self.recording_analyzer)

        graph_builder.add_edge(START, "recording_analyzer")
        graph_builder.add_edge("recording_analyzer", END)

        self.graph = graph_builder.compile()


    def openai_recording_analyzer(self, events: List[Dict]):

        # Create the prompt.
#         prompt = """
# You are an expert UI/UX Researcher analyzing a user session. You are given a list of events from a rrweb recording. Your task is to analyze the events and provide a detailed, grouped, timestamped analysis of the user's actions, behavior. **Group consecutive timestamps that represent similar or related actions into a single interval.** Each interval should capture a single action or a set of related actions.

# **For each interval, include:**
# - **Start Time:** The first timestamp in the group.
# - **End Time:** The last timestamp in the group.
# - **Detailed Description:** A clear description of the user's actions and observations during the interval.
# - **Issue:** If an issue is detected, provide a detailed description of the issue. If no issue is detected, leave it empty.
# - **Category:** Classify the interval as one of the following:
#   - **BUG:** Issues that significantly impact functionality and need immediate resolution.
#   - **USABILITY_ISSUE:** Problems that hinder user experience but do not completely break functionality.
#   - **PERFORMANCE_ISSUE:** Concerns related to speed, load times, or responsiveness. Only mark as performance issue if the loading time is more than 3 seconds.
#   - **ENHANCEMENT:** Suggestions for improvements or new features to enhance the user experience.
#   - **NORMAL:** Routine user actions without any apparent issues. 
#   *Note: If any issue is detected, it should override the NORMAL categorization.*
# - **Short Title:** A short title for the interval.
# - **Timestamp Descriptions:** A list of timestamp descriptions for every timestamp included in the interval. Contains the following fields:
#     - **Description:** A detailed description of the user's actions and observations during the interval.
#     - **Timestamp:** The timestamp in the recording. Format: HH:MM:SS


# **Focus Areas:**
# 1. **User Behavior & Interaction:**
#    - Identify signs of user frustration (e.g., rapid or repeated clicks, hesitations, or abrupt movements).
#    - Examine navigation patterns, particularly moments of hesitation or repeated attempts.
#    - Highlight any moments where the user appears confused or stuck.

# 2. **Interaction with UI Elements:**
#    - Assess how users interact with buttons, menus, forms, and other interactive elements.
#    - Detect if UI elements (e.g., buttons, links, icons) are unresponsive, misplaced, or unclear.
#    - Note if tooltips, modals, or error messages appear and whether they aid or confuse the user.


# 4. **Accessibility:**
#    - Check if UI elements are accessible (e.g., adequate size for click/tap, keyboard navigation support).
#    - Assess whether error messages and labels are clear and assistive.
#    - Note any potential barriers for users with visual or motor impairments.

# 5. **Performance & Responsiveness:**
#    - Observe any lag, slow load times, or sudden reflows of the UI.
#    - Identify any elements that are unresponsive or cause delays in the user's workflow.

# 6. **Error Handling & Feedback:**
#    - Document any bugs or errors that occur and how the UI communicates them.
#    - Note if error messages or feedback mechanisms are helpful and clear.

# 7. **Opportunities for Enhancement:**
#    - Suggest improvements for usability and overall design.
#    - Recommend new features or refinements that could streamline user interactions.
#    - Provide actionable insights to improve the user experience (e.g., "Increase button size for better touch targets," "Improve color contrast for readability").

# **Instructions:**

# - **Grouping:**  
#   - **Group consecutive timestamps** that reflect a single action or a set of related actions into one interval.
#   - If a timestamp clearly represents a distinct action not related to its neighbors, it should start a new interval.
  
# - **Comprehensiveness:**  
#   - Ensure that every provided timestamp is included in the analysis either as its own interval or as part of a grouped interval.
#   - Provide both macro-level (overall session behavior) and micro-level (detailed UI element interactions) insights.

# - **Clarity:**  
#   - Use clear, concise language. Reference specific timestamps, UI elements, and user behaviors.
  
# - **Actionable Insights:**  
#   - Provide concrete recommendations for each identified issue, prioritizing bugs and usability issues over normal interactions.

# - **Final Check:**  
#   - Before finalizing your analysis, verify that every provided timestamp is included in the output and appropriately grouped into intervals based on similarity of actions.
        
#                     """


        prompt = """
You are an AI agent tasked with analyzing user session recordings based on rrweb events. Your input is a JSON object containing an array of events. Each event includes a timestamp (formatted as HH:MM:SS), a type, and additional details. Your goal is to produce a detailed analysis of the session by grouping events into intervals and providing a comprehensive description of the user's actions. Your final output must follow the JSON schema defined below.

### Structured Output Schema

1. **TimestampDescription**  
   Each object in this list represents an individual event’s description at a specific timestamp.  
   - **timestamp**: A string in HH:MM:SS format representing the time of the event.  
   - **description**: A detailed explanation of what the user did or what happened on the screen at that timestamp.

2. **TimestampInterval**  
   Each interval groups several events together and provides an overall description and analysis, including any issues found.  
   - **start_time**: Start time of the interval in HH:MM:SS.  
   - **end_time**: End time of the interval in HH:MM:SS.  
   - **description**: A detailed description of the user's actions during the interval.  
   - **issue** (optional): If any issue is detected in the interval, provide a concise description; otherwise, leave it empty.  
   - **category**: One of the following values: NORMAL, BUG, USABILITY_ISSUE, PERFORMANCE_ISSUE, or ENHANCEMENT.  
   - **short_title**: A brief title summarizing the interval.  
   - **timestamp_descriptions**: An array of TimestampDescription objects. Ensure that every event timestamp is accounted for in this list.

3. **RecordingAnalysis**  
   This is the overall output that summarizes the entire recording.  
   - **intervals**: An array of TimestampInterval objects.  
   - **summary**: A summary that includes an overview of the user’s actions, behavior, emotional state, any issues found, and recommendations for improvement.

### Instructions for the Analysis

- **Grouping Events into Intervals:**  
  Analyze the provided events and group them into logical intervals. For each interval, define the start and end times, and include a detailed description of what happens within that period.  
- **Detailed Descriptions:**  
  For every event timestamp within an interval, include a corresponding TimestampDescription that details the action (e.g., page navigation, mouse movement, input changes, scrolling activity).
- **Detecting Issues:**  
  If you identify potential issues (such as bugs, usability concerns, performance delays, or possible areas for enhancement), note these in the “issue” field and categorize the interval accordingly using the following options:  
  - NORMAL  
  - BUG  
  - USABILITY_ISSUE  
  - PERFORMANCE_ISSUE  
  - ENHANCEMENT  
- **Use the Provided Sample Data:**  
  For example, consider the following events in your analysis:
  - A navigation event to `http://localhost:3000/login` at `00:00`.
  - Mouse movements with varying durations, distances, and patterns.
  - Input changes (e.g., email and password fields) at specific timestamps.
  - Scrolling activities with details such as scroll pattern and distances.
- **Output Format:**  
  Your output must be valid JSON that adheres exactly to the defined structure, without any additional fields.

### Final Output

Your final output should be a JSON object of type `RecordingAnalysis` that contains the intervals (each with its respective timestamp descriptions) and a summary of the overall recording analysis.
"""
                    

        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=json.dumps(events)),
        ]

        response = self.openai_llm.with_structured_output(RecordingAnalysis).invoke(
            messages
        )
        return response

    def recording_analyzer(self, state: State, config: RunnableConfig) -> dict:
        events = state["events"]
        response = self.openai_recording_analyzer(events)

        return {"recording_analysis": response}


    def get_graph(self):
        return self.graph

    @observe()
    def analyze_recording(
        self,
        org_id: str,
        recording_id: str,
        events: List[Dict],
    ) -> dict:

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
            # Convert any Decimal objects in events to float
            events_json = json.dumps(events, cls=DecimalEncoder)
            events_parsed = json.loads(events_json)
            
            resp = self.graph.invoke(
                {"events": events_parsed},
                config=config,
                # debug=True
            )
            return resp
        except Exception as e:
            logger.error(f"Error creating graph with response: {str(e)}")
            raise e
