import cv2
import numpy as np
from typing import List, Tuple
import os

def preprocess_recording(recording_path: str, frames_per_second: int = 1) -> List[Tuple[int, List[np.ndarray]]]:
    """
    Preprocesses a video recording by splitting it into 30-second intervals and extracting
    frames at specified rate for each interval.
    
    Args:
        recording_path (str): Path to the video recording file
        frames_per_second (int): Number of frames to extract per second (default: 1)
        
    Returns:
        List[Tuple[int, List[np.ndarray]]]: List of tuples containing:
            - Start time of the interval in seconds
            - List of frames (as numpy arrays) for that 30-second interval
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
    
    intervals = []
    interval_duration = 30  # seconds
    
    # Calculate frame step to achieve desired frames per second
    frame_step = fps // frames_per_second
    if frame_step < 1:
        frame_step = 1  # Can't extract more frames than original video
    
    # Process each 30-second interval
    for interval_start in range(0, int(duration), interval_duration):
        interval_frames = []
        
        # Extract multiple frames per second
        for second in range(interval_duration):
            for frame_idx in range(frames_per_second):
                # Calculate position for evenly spaced frames within the second
                offset = (frame_step * frame_idx) + (frame_step // 2)
                frame_position = (interval_start + second) * fps + offset
                
                # Break if we've reached the end of the video
                if frame_position >= total_frames:
                    break
                    
                # Set frame position and read frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_position)
                ret, frame = cap.read()
                
                if ret:
                    interval_frames.append(frame)
        
        # Only add intervals that have frames
        if interval_frames:
            intervals.append((interval_start, interval_frames))
    
    # Release the video capture
    cap.release()
    
    return intervals

def timestamp_frames(frames: List[np.ndarray], start_time: int, frames_per_second: int) -> List[Tuple[str, np.ndarray]]:
    timestamped_frames = []
    for i, frame in enumerate(frames):
        frame_time = start_time + (i / frames_per_second)
        hours, remainder = divmod(frame_time, 3600)
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
        aspect = width / float(w)
        dim = (int(w * aspect), height)
    else:
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

# if __name__ == "__main__":
#     intervals = preprocess_recording("recordings/test2.mov", 2)
#     start_time, frames = intervals[1]
#     timestamped_frames = timestamp_frames(frames, start_time, 2)
#     for timestamp, frame in timestamped_frames:
#         print(timestamp)
    
#     # Resize frames to standard width
#     resized_frames = [resize_frame(frame, width=1280) for frame in frames]
    
#     # Analyze changes between frames
#     changes = analyze_frame_changes(resized_frames)
    
#     # Enhance frames with slightly increased brightness and contrast
#     enhanced_frames = [enhance_frame(frame, brightness=1.1, contrast=1.2) for frame in resized_frames]
    
#     # Create enhanced video
#     create_video_from_frames(enhanced_frames, "recordings/output_enhanced.mp4")