from enum import Enum

class RecordingType(str, Enum):
    ORIGINAL = 'original'
    ONE_FRAME_PER_SECOND = 'one_frame_per_second'

class VideoType(str, Enum):
    MP4 = 'video/mp4'
    QUICKTIME = 'video/quicktime'
    X_MSVIDEO = 'video/x-msvideo'
    X_MATROSKA = 'video/x-matroska'
    WEBM = 'video/webm'
    MPEG = 'video/mpeg'
    OGG = 'video/ogg'
    # for testing purposes
    JPEG = 'image/jpeg'

class IntervalCategory(Enum):
    NORMAL = "Normal"
    BUG = "Bug"
    USABILITY_ISSUE = "Usability Issue"
    PERFORMANCE_ISSUE = "Performance Issue"
    ENHANCEMENT = "Enhancement"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"