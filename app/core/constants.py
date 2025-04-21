class APIPath:
    # API Versions
    V1 = "/api/v1"


class SQSQueueConfig:
    # Default SQS queue configuration
    MAX_MESSAGES = 10
    WAIT_TIME_SECONDS = 20  # Long polling
    VISIBILITY_TIMEOUT = 600  # 10 minutes
