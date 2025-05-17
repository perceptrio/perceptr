import os
import cv2
from typing import List, Tuple, Dict
import subprocess
import shutil

# Map MIME types to file extensions and OpenCV codecs
MIME_TO_EXTENSION: Dict[str, str] = {
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-msvideo": ".avi",
    "video/x-matroska": ".mkv",
    "video/webm": ".webm",
    "video/mpeg": ".mpeg",
    "video/ogg": ".ogv",
}

EXTENSION_TO_CODEC: Dict[str, str] = {
    ".mp4": "avc1",    # H.264 codec for MP4
    ".mov": "mp4v",    # Default codec for QuickTime
    ".avi": "XVID",    # XVID codec for AVI
    ".mkv": "mp4v",    # Default codec for Matroska
    ".webm": "VP90",   # VP9 codec for WebM
    ".mpeg": "mp4v",   # Default codec for MPEG
    ".ogv": "THEO",    # Theora codec for Ogg
    ".ogx": "THEO",    # Theora codec for Ogg
    # Default for any other extension
    "": "mp4v"
}

def get_extension_from_mime(mime_type: str) -> str:
    """Get the file extension for a MIME type."""
    return MIME_TO_EXTENSION.get(mime_type, ".mp4")

def get_codec_for_extension(extension: str) -> str:
    """Get the appropriate codec fourcc string for a file extension."""
    extension = extension.lower()
    return EXTENSION_TO_CODEC.get(extension, "mp4v")

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

def is_ffmpeg_available() -> bool:
    """
    Check if FFmpeg is available on the system.
    
    Returns:
        bool: True if FFmpeg is available, False otherwise
    """
    return shutil.which("ffmpeg") is not None

def ffmpeg_get_video_duration(video_path: str) -> float:
    """
    Get the duration of a video using FFprobe (from FFmpeg suite).
    
    Args:
        video_path (str): Path to the video file
        
    Returns:
        float: Duration in seconds
    """
    import json
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Check if FFmpeg is available
    if not is_ffmpeg_available():
        raise RuntimeError("FFmpeg is not available on the system")
    
    try:
        # Use ffprobe instead of ffmpeg for more efficient metadata extraction
        cmd = [
            'ffprobe', 
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        duration = float(data['format']['duration'])
        return duration
    except subprocess.CalledProcessError as e:
        print(f"FFprobe duration error: {e.stderr}")
        # Fall back to OpenCV method if FFprobe fails
        return get_recording_duration(video_path)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        print(f"Error parsing FFprobe output: {e}")
        # Fall back to OpenCV method if parsing fails
        return get_recording_duration(video_path)

def ffmpeg_slow_down_video(
    video_path: str,
    output_path: str,
    slowdown_factor: float = 2.0,
    use_hardware_accel: bool = True
) -> None:
    """
    Create a slowed-down version of a video using FFmpeg.
    
    Args:
        video_path (str): Path to the source video file
        output_path (str): Path to save the slowed-down video
        slowdown_factor (float): Factor by which to slow down the video (e.g., 2.0 for half speed)
        use_hardware_accel (bool): Whether to use hardware acceleration if available
        
    Raises:
        ValueError: If the operation fails
        FileNotFoundError: If the file does not exist
    """
    import subprocess
    import platform
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Check if FFmpeg is available
    if not is_ffmpeg_available():
        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. Please install FFmpeg to use this feature.\n"
            "- macOS: brew install ffmpeg\n"
            "- Ubuntu/Debian: sudo apt install ffmpeg\n"
            "- Windows: Download from https://ffmpeg.org/download.html"
        )
    
    # Detect input and output format
    _, input_ext = os.path.splitext(video_path)
    _, output_ext = os.path.splitext(output_path)
    input_ext = input_ext.lower()
    output_ext = output_ext.lower()
    
    # Prepare hardware acceleration if enabled
    hw_accel = []
    if use_hardware_accel:
        system = platform.system().lower()
        if system == 'darwin':  # macOS
            hw_accel = ['-hwaccel', 'videotoolbox']
        elif system == 'windows':
            # Try NVIDIA first
            try:
                nvidia_check = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
                if nvidia_check.returncode == 0:
                    hw_accel = ['-hwaccel', 'cuda']
                else:
                    hw_accel = ['-hwaccel', 'dxva2']
            except Exception:
                hw_accel = ['-hwaccel', 'auto']
        elif system == 'linux':
            try:
                nvidia_check = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
                if nvidia_check.returncode == 0:
                    hw_accel = ['-hwaccel', 'cuda']
                else:
                    hw_accel = ['-hwaccel', 'vaapi']
            except Exception:
                hw_accel = ['-hwaccel', 'auto']
    
    # Handle audio slowdown within FFmpeg's capabilities (0.5x - 2.0x)
    speed = 1/slowdown_factor
    audio_filter = []
    
    if 0.5 <= speed <= 2.0:
        audio_filter = ['-filter:a', f'atempo={speed}']
    else:
        # For more extreme slowdowns, we skip audio to avoid distortion
        audio_filter = ['-an']  # No audio
    
    try:
        # Base command with hardware acceleration if enabled
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output files
            *hw_accel,
            '-i', video_path,
            '-filter:v', f'setpts={slowdown_factor}*PTS',  # Slow down video
            *audio_filter
        ]
        
        # Add codec options based on output format
        if output_ext == '.webm':
            # WebM requires VP8, VP9 or AV1
            cmd.extend(['-c:v', 'libvpx-vp9'])
        elif use_hardware_accel and system == 'darwin' and output_ext in ['.mp4', '.mov']:
            # Use hardware encoding on Mac if available
            cmd.extend(['-c:v', 'h264_videotoolbox'])
        elif use_hardware_accel and system == 'windows' and nvidia_check.returncode == 0:
            # Use NVIDIA hardware encoding if available
            cmd.extend(['-c:v', 'h264_nvenc'])
        else:
            # Let FFmpeg choose the best codec for the container
            # This will typically be h264 for MP4/MOV, etc.
            cmd.extend(['-c:v', 'libx264', '-preset', 'fast'])
        
        # Add output path
        cmd.append(output_path)
        
        print(f"Running FFmpeg to slow down video: {' '.join(cmd)}")
        process = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Verify output file was created with significant size
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:  # At least 1KB
            raise ValueError(f"Failed to create valid output video at {output_path}")
            
        print(f"Successfully created slowed video at {output_path}")
        
    except subprocess.CalledProcessError as e:
        error_message = f"FFmpeg error: {e.stderr}"
        print(error_message)
        raise ValueError(error_message)

def ffmpeg_chunk_video(
    video_path: str, 
    chunk_size_seconds: int = 30,
    output_dir: str = None,
    codec: str = None  # Let's make this optional and auto-detect
) -> List[Tuple[str, float, float]]:
    """
    Split a video into chunks of specified duration using FFmpeg.

    Args:
        video_path (str): Path to the source video file
        chunk_size_seconds (int): Size of each chunk in seconds
        output_dir (str, optional): Directory to save chunks. If None, uses the directory of the source video.
        codec (str, optional): Video codec to use. If None, auto-detects based on file extension.

    Returns:
        List[Tuple[str, float, float]]: List of tuples containing (chunk_path, start_time, duration) for each chunk

    Raises:
        ValueError: If the operation fails
        FileNotFoundError: If the file does not exist
    """
    import math
    
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
        
    # Check if FFmpeg is available
    if not is_ffmpeg_available():
        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. Please install FFmpeg to use this feature.\n"
            "- macOS: brew install ffmpeg\n"
            "- Ubuntu/Debian: sudo apt install ffmpeg\n"
            "- Windows: Download from https://ffmpeg.org/download.html"
        )

    # Get or create output directory
    if output_dir is None:
        output_dir = os.path.dirname(video_path)
    
    # Extract base filename and extension for creating chunk names
    base_name = os.path.basename(video_path)
    base_filename, file_ext = os.path.splitext(base_name)
    file_ext = file_ext.lower()
    
    # Get codec options if a specific codec was requested
    codec_options = []
    if codec:
        codec_options = ['-c:v', codec]
    elif file_ext == '.webm':
        # WebM requires VP8, VP9 or AV1
        codec_options = ['-c:v', 'libvpx-vp9']
    
    # Make sure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    try:
        # Get video duration using FFmpeg
        try:
            total_duration = ffmpeg_get_video_duration(video_path)
        except Exception as e:
            print(f"Error getting duration with FFprobe: {e}")
            # Fall back to OpenCV if FFmpeg fails
            total_duration = get_recording_duration(video_path)
        
        # Calculate number of chunks
        chunk_count = math.ceil(total_duration / chunk_size_seconds)
        
        # Optimize: for small videos with few chunks (1-3), it's faster to extract in a single command
        if chunk_count <= 3:
            return ffmpeg_chunk_video_optimized(video_path, chunk_size_seconds, output_dir, codec, total_duration, file_ext)
        
        # Store information about created chunks
        chunk_info = []
        
        # Create each chunk using segment feature of FFmpeg
        for i in range(chunk_count):
            start_seconds = i * chunk_size_seconds
            duration = min(chunk_size_seconds, total_duration - start_seconds)
            
            if duration <= 0:
                break
                
            # Create a name for the chunk
            chunk_path = os.path.join(output_dir, f"{base_filename}_chunk_{i}{file_ext}")
            
            # Use FFmpeg to extract the chunk - optimize for seeking
            if i == 0:
                # For first chunk, using -ss BEFORE -i is more accurate for the start
                cmd = [
                    'ffmpeg',
                    '-y',  # Overwrite output files
                    '-ss', str(start_seconds),  # Start time
                    '-i', video_path,  # Input file
                    '-t', str(duration),  # Duration
                    *codec_options,  # Video codec options (if specified)
                    '-avoid_negative_ts', '1',  # Handle negative timestamps
                    '-reset_timestamps', '1',  # Reset timestamps
                    chunk_path  # Output file
                ]
            else:
                # For later chunks, using -ss AFTER -i allows for more accurate frame selection
                cmd = [
                    'ffmpeg',
                    '-y',  # Overwrite output files
                    '-i', video_path,  # Input file
                    '-ss', str(start_seconds),  # Start time
                    '-t', str(duration),  # Duration
                    *codec_options,  # Video codec options (if specified)
                    '-avoid_negative_ts', '1',  # Handle negative timestamps
                    '-reset_timestamps', '1',  # Reset timestamps
                    chunk_path  # Output file
                ]
            
            print(f"Creating chunk {i+1}/{chunk_count} from {start_seconds}s to {start_seconds + duration}s")
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Verify the chunk was created successfully
            if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) == 0:
                raise ValueError(f"Failed to create valid chunk at {chunk_path}")
            
            # Add chunk info to the result
            chunk_info.append((chunk_path, start_seconds, duration))
            
        return chunk_info
        
    except subprocess.CalledProcessError as e:
        error_message = f"FFmpeg error: {e.stderr}"
        print(error_message)
        raise ValueError(error_message)
    
    return []

def ffmpeg_chunk_video_optimized(
    video_path: str, 
    chunk_size_seconds: int = 30,
    output_dir: str = None,
    codec: str = None,
    total_duration: float = None,
    file_ext: str = None
) -> List[Tuple[str, float, float]]:
    """
    Split a video into chunks using FFmpeg's segment feature.
    This is optimized for a small number of chunks.
    
    Args:
        Same as ffmpeg_chunk_video
        
    Returns:
        List of chunk information
    """
    import math
    
    # Get or create output directory
    if output_dir is None:
        output_dir = os.path.dirname(video_path)
    
    # Extract base filename and extension for creating chunk names if not provided
    if file_ext is None:
        base_name = os.path.basename(video_path)
        base_filename, file_ext = os.path.splitext(base_name)
        file_ext = file_ext.lower()
    else:
        base_name = os.path.basename(video_path)
        base_filename, _ = os.path.splitext(base_name)
    
    # Get codec options if a specific codec was requested
    codec_options = []
    if codec:
        codec_options = ['-c:v', codec]
    elif file_ext == '.webm':
        # WebM requires VP8, VP9 or AV1
        codec_options = ['-c:v', 'libvpx-vp9']
    
    # Get duration if not provided
    if total_duration is None:
        try:
            total_duration = ffmpeg_get_video_duration(video_path)
        except:
            total_duration = get_recording_duration(video_path)
    
    # Calculate number of chunks
    chunk_count = math.ceil(total_duration / chunk_size_seconds)
    
    # Output pattern for segments
    segment_pattern = os.path.join(output_dir, f"{base_filename}_chunk_%d{file_ext}")
    
    # Create command using segment muxer
    cmd = [
        'ffmpeg',
        '-y',
        '-i', video_path,
        *codec_options,  # Video codec (if specified)
        '-map', '0',
        '-f', 'segment',
        '-segment_time', str(chunk_size_seconds),
        '-reset_timestamps', '1',
    ]
    
    # Add segment format if we can determine it
    if file_ext:
        format_name = file_ext.replace('.', '')  # Remove dot from extension
        if format_name:
            cmd.extend(['-segment_format', format_name])
    
    # Add output pattern
    cmd.append(segment_pattern)
    
    print(f"Creating {chunk_count} chunks in a single command: {' '.join(cmd)}")
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    
    # Collect information about created chunks
    chunk_info = []
    for i in range(chunk_count):
        start_seconds = i * chunk_size_seconds
        duration = min(chunk_size_seconds, total_duration - start_seconds)
        
        if duration <= 0:
            break
            
        chunk_path = os.path.join(output_dir, f"{base_filename}_chunk_{i}{file_ext}")
        
        # Verify chunk exists
        if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
            chunk_info.append((chunk_path, start_seconds, duration))
        else:
            print(f"Warning: Expected chunk {chunk_path} was not created or is empty")
    
    return chunk_info

def slow_down_video(
    video_path: str,
    output_path: str,
    slowdown_factor: float = 2.0
) -> None:
    """
    Create a slowed-down version of a video using OpenCV.
    
    Args:
        video_path (str): Path to the source video file
        output_path (str): Path to save the slowed-down video
        slowdown_factor (float): Factor by which to slow down the video (e.g., 2.0 for half speed)
        
    Raises:
        ValueError: If the video file cannot be opened
        FileNotFoundError: If the file does not exist
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Determine file extensions to select appropriate codec
    _, input_ext = os.path.splitext(video_path)
    _, output_ext = os.path.splitext(output_path)
    
    input_ext = input_ext.lower()
    output_ext = output_ext.lower()
    
    # Open the video file
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    
    try:
        # Get video properties
        original_fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Calculate new FPS for slowed down video
        new_fps = original_fps / slowdown_factor
        
        # Get the appropriate codec for the output extension
        codec_str = get_codec_for_extension(output_ext)
        fourcc = cv2.VideoWriter_fourcc(*codec_str)
        
        # Initialize video writer
        out = cv2.VideoWriter(output_path, fourcc, new_fps, (width, height))
        
        # Check if the writer was opened successfully
        if not out.isOpened():
            # Fall back to mp4v if the chosen codec doesn't work
            print(f"Failed to open video writer with codec {codec_str}, falling back to mp4v")
            fallback_ext = ".mp4" if output_ext != ".mp4" else ".avi"
            fallback_path = output_path.replace(output_ext, fallback_ext)
            fallback_fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(fallback_path, fallback_fourcc, new_fps, (width, height))
            
            if not out.isOpened():
                raise ValueError(f"Failed to create output video with any codec")
            
            # Update output path if we had to use fallback
            output_path = fallback_path
        
        # Process all frames
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            # Write the frame
            out.write(frame)
            frame_count += 1
            
            # Print progress
            if frame_count % 100 == 0:
                progress = (frame_count / total_frames) * 100
                print(f"Processed {frame_count}/{total_frames} frames ({progress:.1f}%)")
        
        # Release resources
        out.release()
        
        # Verify output file was created with non-zero size
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise ValueError(f"Failed to create valid output video at {output_path}")
            
        print(f"Successfully created slowed video at {output_path}")
        
    finally:
        cap.release()
    
    return

def chunk_video(
    video_path: str, 
    chunk_size_seconds: int = 30,
    output_dir: str = None,
    slowdown_factor: float = 1.0
) -> List[Tuple[str, float, float]]:
    """
    Split a video into chunks of specified duration using OpenCV.

    Args:
        video_path (str): Path to the source video file
        chunk_size_seconds (int): Size of each chunk in seconds
        output_dir (str, optional): Directory to save chunks. If None, uses the directory of the source video.
        slowdown_factor (float): Factor by which the video is already slowed down (for timestamp calculation)

    Returns:
        List[Tuple[str, float, float]]: List of tuples containing (chunk_path, start_time, duration) for each chunk

    Raises:
        ValueError: If the video file cannot be opened
        FileNotFoundError: If the file does not exist
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Get or create output directory
    if output_dir is None:
        output_dir = os.path.dirname(video_path)
    
    # Extract base filename and extension for creating chunk names
    base_name = os.path.basename(video_path)
    base_filename, file_ext = os.path.splitext(base_name)
    file_ext = file_ext.lower()
    
    # Open the video file
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    
    try:
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total_duration = total_frames / fps if fps > 0 else 0
        
        # Get the appropriate codec for the file extension
        codec_str = get_codec_for_extension(file_ext)
        fourcc = cv2.VideoWriter_fourcc(*codec_str)
        
        # Calculate number of chunks
        chunk_count = max(1, int(total_duration / chunk_size_seconds) + (1 if total_duration % chunk_size_seconds > 0 else 0))
        
        chunk_info = []
        
        # Create each chunk
        for i in range(chunk_count):
            start_seconds = i * chunk_size_seconds
            duration = min(chunk_size_seconds, total_duration - start_seconds)
            
            if duration <= 0:
                break
            
            # Calculate start and end frames
            start_frame = int(start_seconds * fps)
            end_frame = int((start_seconds + duration) * fps)
            
            # Set position to start frame
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
            
            # Create a name for the chunk
            chunk_path = os.path.join(output_dir, f"{base_filename}_chunk_{i}{file_ext}")
            
            # Create video writer
            out = cv2.VideoWriter(chunk_path, fourcc, fps, (width, height))
            
            # Check if the writer was opened successfully
            if not out.isOpened():
                # Try with a fallback codec if the first one failed
                print(f"Failed to open video writer with codec {codec_str}, trying fallback")
                fallback_ext = ".mp4"
                fallback_path = os.path.join(output_dir, f"{base_filename}_chunk_{i}{fallback_ext}")
                fallback_fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(fallback_path, fallback_fourcc, fps, (width, height))
                
                if not out.isOpened():
                    raise ValueError(f"Could not create chunk video with any codec")
                
                # Update chunk path if we had to use fallback
                chunk_path = fallback_path
            
            # Process frames for this chunk
            frames_written = 0
            frames_to_write = end_frame - start_frame
            
            while frames_written < frames_to_write:
                ret, frame = cap.read()
                if not ret:
                    break
                
                out.write(frame)
                frames_written += 1
            
            # Release the writer
            out.release()
            
            # Verify the chunk was created successfully
            if not os.path.exists(chunk_path) or os.path.getsize(chunk_path) == 0:
                raise ValueError(f"Failed to create valid chunk at {chunk_path}")
            
            # Add chunk info to the result
            chunk_info.append((chunk_path, start_seconds, duration))
            
            print(f"Created chunk {i+1}/{chunk_count} from {start_seconds}s to {start_seconds + duration}s")
            
        return chunk_info
        
    finally:
        cap.release()
    
    return []

