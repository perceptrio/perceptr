from graphs.recording_analyzer_graph import RecordingAnalyzerGraph



def analyze_recording(user_id: str, recording_id: str, recording_path: str) -> dict:
    graph = RecordingAnalyzerGraph()
    response = graph.analyze_recording(user_id, recording_id, recording_path)
    return response["recording_analysis"]