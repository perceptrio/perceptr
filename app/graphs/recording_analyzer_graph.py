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
from logger import get_module_logger
logger = get_module_logger(__name__)
import os
import time
os.environ["LANGFUSE_PUBLIC_KEY"] = settings.LANGFUSE_PUBLIC_KEY
os.environ["LANGFUSE_SECRET_KEY"] = settings.LANGFUSE_PRIVATE_KEY
os.environ["LANGFUSE_HOST"] = settings.LANGFUSE_HOST

import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import Optional, List


# class TimestampDescription(BaseModel):
#     """A timestamp in the recording."""
#     timestamp: str = Field(description="The timestamp in the recording.")
#     description: str = Field(description="A detailed description of the user's actions")
#     bugs: Optional[str] = Field(description="Any bugs or issues found in the recording.")
#     errors: Optional[str] = Field(description="Any errors found in the recording.")
#     recommendations: Optional[str] = Field(description="Any recommendations for improvement.")

# class RecordingAnalysis(BaseModel):
#     """The analysis of the recording."""
#     timestamp_descriptions: List[TimestampDescription] = Field(description="A list of timestamp descriptions.")
#     summary: str = Field(description="A summary of the user's behavior, emotional state, and recommendations for improvement.")


class RecordingAnalysis(BaseModel):
    """Analysis of a user session recording."""
    timestamps: List[str] = Field(description="The timestamps in the recording.")
    descriptions: List[str] = Field(description="For each timestamp, a detailed description of the user's actions. Add the timestamp to the description.")
    bugs: Optional[str] = Field(description="Any bugs or issues found in the recording. Add the timestamp to the bug description.")
    errors: Optional[str] = Field(description="Any errors found in the recording. Add the timestamp to the error description.")
    recommendations: Optional[str] = Field(description="Any recommendations for improvement. Add the timestamp to the recommendation description.")
    summary: str = Field(description="A summary of the user's behavior, emotional state, and recommendations for improvement.")


class State(TypedDict):
    recording_path: str
    recording_analysis: RecordingAnalysis


class RecordingAnalyzerGraph():
    def __init__(self):
        graph_builder = StateGraph(State)
        self.openai_llm = ChatOpenAI(api_key=settings.OPENAI_API_KEY, model="gpt-4o-2024-08-06", streaming=True, temperature=0)
        self.gemini_llm = ChatGoogleGenerativeAI(api_key=settings.GEMINI_API_KEY, model="gemini-2.0-flash-exp", streaming=True, temperature=0)
        genai.configure(api_key=settings.GEMINI_API_KEY)

        graph_builder.add_node("recording_analyzer", self.recording_analyzer)


        graph_builder.add_edge(START, "recording_analyzer")
        graph_builder.add_edge("recording_analyzer", END)

        self.graph = graph_builder.compile()


    def recording_analyzer(self, state: State, config: RunnableConfig) -> dict:
        logger.info("Uploading file...")
        recording_path = state["recording_path"]
        uploaded_recording = genai.upload_file(path=recording_path)
        logger.info(f"Completed upload: {uploaded_recording.uri}")

        # Check whether the file is ready to be used.
        while uploaded_recording.state.name == "PROCESSING":
            print('.', end='')
            time.sleep(5)
            uploaded_recording = genai.get_file(uploaded_recording.name)

        if uploaded_recording.state.name == "FAILED":
            raise ValueError(uploaded_recording.state.name)
        
        logger.info(f"File ready: {uploaded_recording.uri}")

        # Create the prompt.
        prompt =  """You are an expert UI/UX Researcher analyzing a user session.
        For each timestamp in the recording, provide a detailed analysis of the user's behavior and emotional state.
        
         Focus on:
                    1. Signs of user frustration (rapid movements, rage clicks)
                    2. Navigation patterns and hesitation points
                    3. Areas where the user seems confused or stuck
                    4. Interaction with specific UI elements
                    5. Bugs and issues
                    6. Errors and issues
                    
        Then at the end, provide a summary of the user's behavior, emotional state, and recommendations for improvement.
        
                    """

        messages = [
            HumanMessage(content=[{
            "type": "media",
            "mime_type": uploaded_recording.mime_type,
            "file_uri": uploaded_recording.uri
        },]),
            HumanMessage(content=prompt)
        ]

        response = self.gemini_llm.with_structured_output(RecordingAnalysis).invoke(messages)
        logger.info(f"Response: {response}")
        

        return {
            "recording_analysis": response
        }


    def get_graph(self):
        return self.graph

    @observe()
    def analyze_recording(self, user_id: str, recording_id: str, recording_path: str) -> dict:

        langfuse_context.update_current_trace(
            session_id=recording_id,
            user_id=user_id,
        )

        langfuse_handler = langfuse_context.get_current_langchain_handler()

        config = {
            "configurable": {
                # Checkpoints are accessed by thread_id
                "thread_id": recording_id,
            },
            "callbacks": [langfuse_handler]
        }
        try:
            resp = self.graph.invoke(
                {
                    "recording_path": "recordings/" + recording_path,
                },
                config=config,
                # debug=True
            )
            return resp
        except Exception as e:
            logger.error("Error creating graph with response", {"error": str(e)})
            raise e


    
