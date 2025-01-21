from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # OpenAI and LangFuse settings
    OPENAI_API_KEY: str
    GEMINI_API_KEY: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_PRIVATE_KEY: str
    LANGFUSE_HOST: str

    # Database settings
    DATABASE_URL: str = "postgresql://user:password123@localhost:5432/perceptr"
    
    # JWT settings
    SECRET_KEY: str = "your-secret-key-here"  # Change this in production!
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    class Config:
        env_file = ".env"

settings = Settings()