import os
import cv2

def get_recording_duration(recording_path: str) -> float:
    """
    Get the duration of a video recording in seconds.
    This is a fast operation as it only reads metadata without processing frames.

    Args:
        recording_path (str): Path to the video file

    Returns:
        float: Duration in seconds

    Raises:
        ValueError: If the video file cannot be opened
        FileNotFoundError: If the file does not exist
    """
    if not os.path.exists(recording_path):
        raise FileNotFoundError(f"Recording file not found: {recording_path}")

    cap = cv2.VideoCapture(recording_path)
    if not cap.isOpened():
        cap.release()
        raise ValueError(f"Could not open video file: {recording_path}")

    try:
        # Try getting duration directly first
        duration = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

        # If direct duration is 0 or seems incorrect, calculate from frames
        if duration <= 0:
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if fps > 0:  # Avoid division by zero
                duration = total_frames / fps

        return float(duration)
    finally:
        cap.release()  # Always release the capture object

def get_file_size(file_path: str) -> int:
    """
    Get the size of a file in bytes.
    """
    return os.path.getsize(file_path)

