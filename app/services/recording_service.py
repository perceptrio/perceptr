from graphs.recording_analyzer_graph import RecordingAnalyzerGraph
from utils.recording import preprocess_recording, timestamp_frames, resize_frame


FRAMES_PER_SECOND = 1
RECORDINGS_PREFIX = "recordings/"
FRAME_HEIGHT = 512

def analyze_recording(user_id: str, recording_id: str, recording_path: str) -> dict:

    graph = RecordingAnalyzerGraph()
    recording_path = f"{RECORDINGS_PREFIX}/{recording_path}"
    preprocessed_recording_intervals = preprocess_recording(recording_path, frames_per_second=FRAMES_PER_SECOND)
    response = []
    # last_three_intervals = preprocessed_recording_intervals[-2:]
    for interval in preprocessed_recording_intervals:
        start_time, frames_with_times = interval
        print(f"Processing interval {start_time}")
        resized_frames = [(t, resize_frame(f, height=FRAME_HEIGHT)) for t, f in frames_with_times]
        timestamped_frames = timestamp_frames(resized_frames, start_time, FRAMES_PER_SECOND)
        interval_response = graph.analyze_recording(user_id, recording_id, recording_path, timestamped_frames)
        response.append(interval_response["recording_analysis"].json())

    return response