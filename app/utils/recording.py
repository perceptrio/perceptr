import cv2
import numpy as np
from typing import List, Tuple
import os

def preprocess_recording(recording_path: str, frames_per_second: int = 1) -> List[Tuple[int, List[Tuple[float, np.ndarray]]]]:
    """
    Preprocesses a video recording by splitting it into 30-second intervals and extracting
    frames at specified rate for each interval.
    
    Args:
        recording_path (str): Path to the video recording file
        frames_per_second (int): Number of frames to extract per second (default: 1)
        
    Returns:
        List[Tuple[int, List[Tuple[float, np.ndarray]]]]: List of tuples containing:
            - Start time of the interval in seconds
            - List of tuples with exact frame time and frame data for that interval
    """
    if not os.path.exists(recording_path):
        raise FileNotFoundError(f"Recording file not found: {recording_path}")
    
    if frames_per_second <= 0:
        raise ValueError("frames_per_second must be positive")
    
    # Open the video file
    cap = cv2.VideoCapture(recording_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {recording_path}")
    
    # Get video properties
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps
    
    # After opening the video file, add these lines:
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Frame dimensions: {frame_width}x{frame_height}")
    
    intervals = []
    interval_duration = 30  # seconds
    
    # Calculate frame step to achieve desired frames per second
    frame_step = fps // frames_per_second
    if frame_step < 1:
        frame_step = 1  # Can't extract more frames than original video
    
    # Process each 30-second interval
    for interval_start in range(0, int(duration), interval_duration):
        interval_frames = []
        
        # Get the actual frame position at the start of the interval
        interval_start_frame = interval_start * fps
        
        # Extract frames at exact time points
        for second in range(interval_duration):
            for frame_idx in range(frames_per_second):
                # Calculate exact frame position for this time point
                exact_second = second + (frame_idx / frames_per_second)
                frame_position = int(interval_start_frame + (exact_second * fps))
                
                # Break if we've reached the end of the video
                if frame_position >= total_frames:
                    break
                    
                # Set frame position and read frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_position)
                ret, frame = cap.read()
                
                if ret:
                    # Get the actual timestamp from the video
                    actual_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                    exact_time = actual_msec / 1000.0  # Convert milliseconds to seconds
                    interval_frames.append((exact_time, frame))
        
        # Only add intervals that have frames
        if interval_frames:
            intervals.append((interval_start, interval_frames))
    
    # Release the video capture
    cap.release()
    
    return intervals

def extract_all_frames(recording_path: str, frames_per_second: int = 1) -> List[Tuple[str, np.ndarray]]:
    """
    Extracts frames from a video at specified rate with their exact timestamps.
    
    Args:
        recording_path (str): Path to the video recording file
        frames_per_second (int): Number of frames to extract per second (default: 1)
        
    Returns:
        List[Tuple[str, np.ndarray]]: List of tuples containing:
            - Formatted timestamp string in HH:MM:SS format
            - Frame data as numpy array
    """
    if not os.path.exists(recording_path):
        raise FileNotFoundError(f"Recording file not found: {recording_path}")
    
    if frames_per_second <= 0:
        raise ValueError("frames_per_second must be positive")
    
    # Open the video file
    cap = cv2.VideoCapture(recording_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {recording_path}")
    
    # Get video properties
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    duration = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0  # Get duration in seconds
    
    # If duration is 0, calculate it from frames (fallback)
    if duration == 0:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
    
    frames = []
    seen_timestamps = set()
    
    # Read first frame to get dimensions
    ret, first_frame = cap.read()
    if not ret:
        raise ValueError("Could not read first frame from video")
    
    # Extract frames at exact time points
    for second in range(int(duration)):
        for frame_idx in range(frames_per_second):
            # Calculate exact time for this frame
            exact_second = second + (frame_idx / frames_per_second)
            
            # Set position in milliseconds for more accurate seeking
            cap.set(cv2.CAP_PROP_POS_MSEC, exact_second * 1000)
            ret, frame = cap.read()
            
            if ret:
                # Format timestamp as HH:MM:SS
                hours, remainder = divmod(exact_second, 3600)
                minutes, seconds = divmod(remainder, 60)
                timestamp = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
                
                # Only add frame if we haven't seen this timestamp before
                if timestamp not in seen_timestamps:
                    frames.append((timestamp, frame))
                    seen_timestamps.add(timestamp)
            else:
                # If we can't read a frame, we've reached the end
                break
        
        if not ret:
            break
    
    # Release the video capture
    cap.release()
    
    return frames

def timestamp_frames(frames: List[Tuple[float, np.ndarray]], start_time: int, frames_per_second: int) -> List[Tuple[str, np.ndarray]]:
    """
    Convert frames with exact timestamps into formatted timestamp strings.
    
    Args:
        frames: List of tuples containing (exact_time, frame)
        start_time: Start time of the interval (not used anymore as we have exact times)
        frames_per_second: Frames per second (not used anymore as we have exact times)
    """
    timestamped_frames = []
    for exact_time, frame in frames:
        hours, remainder = divmod(exact_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        timestamp = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        timestamped_frames.append((timestamp, frame))
    return timestamped_frames

def create_video_from_frames(frames: List[np.ndarray], output_path: str, fps: int = 1) -> str:
    """
    Creates a video file from a list of frames.
    
    Args:
        frames (List[np.ndarray]): List of frames to convert to video
        output_path (str): Path where the video should be saved
        fps (int): Frames per second for the output video (default: 1)
        
    Returns:
        str: Path to the created video file
    """
    if not frames:
        raise ValueError("No frames provided to create video")
    
    # Get dimensions from the first frame
    height, width = frames[0].shape[:2]
    
    # Create video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    # Write frames to video
    for frame in frames:
        out.write(frame)
    
    # Release the video writer
    out.release()
    
    return output_path

def slow_down_video(frames: List[np.ndarray], slowdown_factor: float = 2.0) -> List[np.ndarray]:
    """
    Slows down a video by duplicating frames.
    
    Args:
        frames (List[np.ndarray]): Original list of frames
        slowdown_factor (float): Factor by which to slow down the video (e.g., 2.0 for half speed)
        
    Returns:
        List[np.ndarray]: New list of frames with duplicated frames for slowdown effect
    """
    if slowdown_factor <= 0:
        raise ValueError("Slowdown factor must be positive")
    
    # Calculate how many times each frame should be repeated
    repeat_count = int(round(slowdown_factor))
    
    # Create new list with duplicated frames
    slowed_frames = []
    for frame in frames:
        slowed_frames.extend([frame.copy() for _ in range(repeat_count)])
    
    return slowed_frames

def resize_frame(frame: np.ndarray, width: int = None, height: int = None) -> np.ndarray:
    """
    Resize frame while maintaining aspect ratio.
    Specify either width or height, the other will be calculated.
    """
    if width is None and height is None:
        return frame
        
    h, w = frame.shape[:2]
    if width is None:
        # Calculate width based on height while maintaining aspect ratio
        aspect = height / float(h)
        dim = (int(w * aspect), height)
    else:
        # Calculate height based on width while maintaining aspect ratio
        aspect = width / float(w)
        dim = (width, int(h * aspect))
        
    return cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)

def detect_motion(frame1: np.ndarray, frame2: np.ndarray, threshold: int = 30) -> Tuple[bool, np.ndarray]:
    """
    Detect motion between two frames.
    Returns (motion_detected, diff_frame)
    """
    # Convert to grayscale
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    
    # Calculate absolute difference
    diff = cv2.absdiff(gray1, gray2)
    
    # Apply threshold
    _, thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)
    
    # Calculate percentage of changed pixels
    change_percent = (thresh > 0).mean() * 100
    
    return change_percent > 1.0, thresh

def enhance_frame(frame: np.ndarray, brightness: float = 1.0, contrast: float = 1.0) -> np.ndarray:
    """
    Enhance frame by adjusting brightness and contrast.
    brightness > 1 increases brightness, < 1 decreases it
    contrast > 1 increases contrast, < 1 decreases it
    """
    enhanced = cv2.convertScaleAbs(frame, alpha=contrast, beta=brightness)
    return enhanced

def detect_text_regions(frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """
    Detect potential text regions in the frame.
    Returns list of (x, y, w, h) coordinates of potential text regions.
    """
    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Apply threshold to get black and white image
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter contours that might be text
    text_regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w > 15 and h > 8:  # Filter out very small regions
            text_regions.append((x, y, w, h))
    
    return text_regions

def analyze_frame_changes(frames: List[np.ndarray]) -> List[Tuple[int, float, np.ndarray]]:
    """
    Analyze changes between consecutive frames.
    Returns list of (frame_index, change_percentage, diff_frame)
    """
    changes = []
    for i in range(1, len(frames)):
        motion_detected, diff_frame = detect_motion(frames[i-1], frames[i])
        if motion_detected:
            change_percent = (diff_frame > 0).mean() * 100
            changes.append((i, change_percent, diff_frame))
    return changes

def save_frame_to_image(frame: np.ndarray, output_path: str) -> None:
    cv2.imwrite(output_path, frame)

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
            
        return duration
    finally:
        cap.release()  # Always release the capture object

# if __name__ == "__main__":
#     intervals = preprocess_recording("recordings/test2.mov", 1)
    # start_time, frames = intervals[1]
    # timestamped_frames = timestamp_frames(frames, start_time, 2)
    # for timestamp, frame in timestamped_frames:
    #     print(timestamp)
    
    # # Resize frames to standard width
    # resized_frames = [resize_frame(frame, width=1280) for frame in frames]
    
    # # Analyze changes between frames
    # changes = analyze_frame_changes(resized_frames)
    
    # # Enhance frames with slightly increased brightness and contrast
    # enhanced_frames = [enhance_frame(frame, brightness=1.1, contrast=1.2) for frame in resized_frames]
    
    # # Create enhanced video
    # create_video_from_frames(enhanced_frames, "recordings/output_enhanced.mp4")