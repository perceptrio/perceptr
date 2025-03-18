from enum import Enum


class RecordingType(str, Enum):
    ORIGINAL = "original"
    ONE_FRAME_PER_SECOND = "one_frame_per_second"


class VideoType(str, Enum):
    MP4 = "video/mp4"
    QUICKTIME = "video/quicktime"
    X_MSVIDEO = "video/x-msvideo"
    X_MATROSKA = "video/x-matroska"
    WEBM = "video/webm"
    MPEG = "video/mpeg"
    OGG = "video/ogg"
    JSON = "application/json"
    # for testing purposes
    JPEG = "image/jpeg"


class IntervalCategory(Enum):
    NORMAL = "NORMAL"
    BUG = "BUG"
    USABILITY_ISSUE = "USABILITY_ISSUE"
    PERFORMANCE_ISSUE = "PERFORMANCE_ISSUE"
    ENHANCEMENT = "ENHANCEMENT"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
