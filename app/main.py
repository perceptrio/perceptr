from contextlib import asynccontextmanager
from typing import AsyncGenerator

from api.v1.analytics.router import router as analytics_router
from api.v1.email.router import router as email_router
from api.v1.issue.router import router as issue_router
from api.v1.org.router import router as org_router
from api.v1.per.router import router as per_router
from api.v1.recording.router import router as recording_router
from api.v1.recording_intervals.router import router as recording_interval_router
from common.services.logger import logger
from common.services.sqs_listener import get_sqs_listener
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup
    try:
        logger.info("Starting SQS listener service...")
        sqs_listener = get_sqs_listener()
        await sqs_listener.start()
        logger.info("SQS listener service started successfully")
    except Exception as e:
        logger.error(f"Failed to start SQS listener service: {str(e)}")

    try:
        yield
    finally:
        # Ensure cleanup happens in finally block
        try:
            logger.info("Stopping SQS listener service...")
            sqs_listener = get_sqs_listener()
            await sqs_listener.stop()
            logger.info("SQS listener service stopped successfully")
        except Exception as e:
            logger.error(f"Error while stopping SQS listener service: {str(e)}")


app = FastAPI(lifespan=lifespan)

# # Create database tables
# Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(org_router)
app.include_router(recording_router)
app.include_router(recording_interval_router)
app.include_router(issue_router)
app.include_router(analytics_router)
app.include_router(email_router)
# SDK router
app.include_router(per_router)


@app.get("/health", response_model=dict[str, str])  # type: ignore
async def health() -> dict[str, str]:
    # Include SQS listener status in health check
    sqs_listener = get_sqs_listener()
    return {
        "status": "ok",
        "sqs_listener": "running" if sqs_listener.is_running else "stopped",
    }


@app.get("/", response_model=dict[str, str])  # type: ignore
async def root() -> dict[str, str]:
    return {"message": "Hello World"}
