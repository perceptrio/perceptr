from typing import Annotated

# from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
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
from typing import Optional, List, Tuple
import numpy as np
from utils.graph import map_timestamped_frames_to_messages

class TimestampDescription(BaseModel):
    """A timestamp in the recording. Use the timestamp to describe the user's actions. Don't miss any timestamp."""
    description: str = Field(description="A detailed description of the user's actions, and what's happening on the screen.")
    timestamp: str = Field(description="The timestamp in the recording. Format: HH:MM:SS")


# class RecordingAnalysis(BaseModel):
#     """The analysis of the recording."""
#     timestamp_descriptions: List[TimestampDescription] = Field(description="A list of timestamp descriptions.")
#     summary: str = Field(description="A summary of the user's behavior, emotional state, and recommendations for improvement.")

class TimestampInterval(BaseModel):
    """A timestamp interval in the recording."""
    start_time: str = Field(description="The start time of the interval in the recording. Format: HH:MM:SS")
    end_time: str = Field(description="The end time of the interval in the recording. Format: HH:MM:SS")
    description: str = Field(description="A detailed description of the user's actions in the interval.")
    category: str = Field(description="The category of the interval. Can be one of: NORMAL, BUG, USEABILITY_ISSUE, PERFORMANCE_ISSUE, ENHANCEMENT")
    issue: Optional[str] = Field(description="The issue found in the interval. If there is no issue, leave it empty.")
    short_title: str = Field(description="A short title for the interval.")
    timestamp_descriptions: List[TimestampDescription] = Field(description="A list of timestamp description in the interval. Don't miss any timestamp.")

class RecordingAnalysis(BaseModel):
    """The intervals of the recording."""
    intervals: List[TimestampInterval] = Field(description="The intervals of the recording.")
    summary: str = Field(description="A summary of the user's actions, behavior, emotional state. Also include any issues found in the recording and recommendations for improvement.")




class State(TypedDict):
    timestamped_frames: List[Tuple[str, np.ndarray]]
    recording_analysis: RecordingAnalysis

class RecordingAnalyzerGraph():
    def __init__(self):
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o", streaming=True, temperature=0)
        self.gemini_llm = ChatGoogleGenerativeAI(api_key=settings.GEMINI_API_KEY, model="gemini-2.0-flash-exp", streaming=True, temperature=0)
        genai.configure(api_key=settings.GEMINI_API_KEY)

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

    
    def openai_recording_analyzer(self, timestamped_frames: List[Tuple[str, np.ndarray]]):
        
                # Create the prompt.
        prompt =  """You are an expert UI/UX Researcher analyzing a user session.
        You are given a list of timestamps along with an image of the user's screen at each timestamp.

        Your task is to analyze the recording and provide a detailed analysis of the user's actions, behavior, and emotional state, by extracting timestamped intervals.

        Each interval should be a single action or a set of actions that are related to each other.

        The intervals should be grouped into categories based on the user's actions.

        The categories are:

        NORMAL: The user is performing their normal actions.

        BUG: Issues that significantly impact functionality and need immediate resolution.

        USEABILITY_ISSUE: Problems that hinder user experience but don't necessarily break functionality.

        PERFORMANCE_ISSUE: Concerns related to speed, load times, or responsiveness.

        ENHANCEMENT: Suggestions for improvements or new features that could enhance user experience.
        

        If any issue is found, it takes priority over the NORMAL category.


        For each timestamp in the recording, provide a detailed analysis of the user's actions, behavior, and emotional state.
        
         Focus on:
                    1. Signs of user frustration (rapid movements, rage clicks)
                    2. Navigation patterns and hesitation points
                    3. Areas where the user seems confused or stuck
                    4. Interaction with specific UI elements
                    5. Bugs and issues
                    6. Errors and issues
                    7. UI/UX issues

        DON'T MISS ANY TIMESTAMP.
        
                    """

        messages = [
            SystemMessage(content=prompt),
            *map_timestamped_frames_to_messages(timestamped_frames)
        ]

        response = self.openai_llm.with_structured_output(RecordingAnalysis).invoke(messages)
        return response


    def recording_analyzer(self, state: State, config: RunnableConfig) -> dict:
        timestamped_frames = state["timestamped_frames"]
        response = self.openai_recording_analyzer(timestamped_frames)
       
        return {
            "recording_analysis": response
        }

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

    #     USEABILITY_ISSUE: Problems that hinder user experience but don't necessarily break functionality.

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

    def get_graph(self):
        return self.graph

    @observe()
    def analyze_recording(self, org_id: str, recording_id: str, timestamped_frames: List[Tuple[str, np.ndarray]]) -> dict:

        langfuse_context.update_current_trace(
            session_id=recording_id,
            user_id=org_id,
        )

        langfuse_handler = langfuse_context.get_current_langchain_handler()

        config = {
            "configurable": {
                # Checkpoints are accessed by thread_id
                "thread_id": recording_id,
                "llm": "OPENAI"
            },
            "callbacks": [langfuse_handler]
        }
        try:
            resp = self.graph.invoke(
                {
                    "timestamped_frames": timestamped_frames
                },
                config=config,
                # debug=True
            )
            return resp
        except Exception as e:
            logger.error("Error creating graph with response", {"error": str(e)})
            raise e


    
