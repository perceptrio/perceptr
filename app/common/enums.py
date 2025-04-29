from enum import Enum


class RecordingType(str, Enum):
    ORIGINAL = "original"
    EVENTS = "events"
    ONE_FRAME_PER_SECOND = "one_frame_per_second"


class VideoType(str, Enum):
    MP4 = "video/mp4"
    QUICKTIME = "video/quicktime"
    X_MSVIDEO = "video/x-msvideo"
    X_MATROSKA = "video/x-matroska"
    WEBM = "video/webm"
    MPEG = "video/mpeg"
    OGG = "video/ogg"
    GZIP = "application/gzip"
    JSON = "application/json"
    # for testing purposes
    JPEG = "image/jpeg"


class IntervalCategory(Enum):
    NORMAL = "NORMAL"
    BUG = "BUG"
    USABILITY_ISSUE = "USABILITY_ISSUE"
    PERFORMANCE_ISSUE = "PERFORMANCE_ISSUE"
    ENHANCEMENT = "ENHANCEMENT"


class IntervalSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class IssueSortBy(str, Enum):
    LATEST = "latest"
    OLDEST = "oldest"
    MOST_AFFECTED = "most_affected"
    LEAST_AFFECTED = "least_affected"


class AnalysisStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class RecordingSessionType(str, Enum):
    RRWEB = "rrweb"
    UPLOADED = "uploaded"
    POSTHOG = "posthog"
    SENTRY = "sentry"
