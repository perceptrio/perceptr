from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # OpenAI and LangFuse settings
    BREVO_API_KEY: str
    OPENAI_API_KEY: str
    GEMINI_API_KEY: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_PRIVATE_KEY: str
    LANGFUSE_HOST: str

    LOG_STYLE: str = "json"
    # Database settings
    DATABASE_URL: str = "postgresql://user:password123@localhost:5432/perceptr"

    # JWT settings
    SECRET_KEY: str = "your-secret-key-here"  # Change this in production!
    REFRESH_SECRET_KEY: str = (
        "your-refresh-secret-key-here"  # Change this in production!
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 365 * 24  # a year

    # AWS settings
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    AWS_BUCKET_NAME: str = "perceptr-recordings-dev"
    SQS_QUEUE_URL: str = ""  # Set this in your .env file

    # AI analysis settings
    AI_ANALYSIS_ENABLED: bool = False
    STALE_SESSION_DURATION: int = 3600  # 1 hour
    RECORDING_INTERVAL_DURATION: int = 30  # 30 seconds
    SLOW_DOWN_FACTOR: float = 2.0

    class Config:
        env_file = ".env"


settings = Settings()
