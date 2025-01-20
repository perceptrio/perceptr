from graphs.recording_analyzer_graph import RecordingAnalyzerGraph
from utils.recording import preprocess_recording, timestamp_frames


FRAMES_PER_SECOND = 1
RECORDINGS_PREFIX = "recordings/"

def analyze_recording(user_id: str, recording_id: str, recording_path: str) -> dict:

    graph = RecordingAnalyzerGraph()
    recording_path = f"{RECORDINGS_PREFIX}/{recording_path}"
    preprocessed_recording_intervals = preprocess_recording(recording_path, frames_per_second=FRAMES_PER_SECOND)
    response = []
    last_three_intervals = preprocessed_recording_intervals[-2:]
    for interval in last_three_intervals:
        start_time, frames_with_times = interval
        timestamped_frames = timestamp_frames(frames_with_times, start_time, FRAMES_PER_SECOND)
        interval_response = graph.analyze_recording(user_id, recording_id, recording_path, timestamped_frames)
        response.append(interval_response["recording_analysis"].json())

    return response