from api.v1.analytics.router import router as analytics_router
from api.v1.chat.router import router as chat_router
from api.v1.chat_message.router import router as chat_message_router
from api.v1.email.router import router as email_router
from api.v1.issue.router import router as issue_router
from api.v1.org.router import router as org_router
from api.v1.per.router import router as per_router
from api.v1.recording.router import router as recording_router
from api.v1.recording_intervals.router import router as recording_interval_router
from api.v1.ws.router import router as ws_router
from common.middleware.app_start import lifespan
from common.middleware.request_logger import RequestLoggerMiddleware
from common.middleware.unhandled_exception import unhandled_exceptions_handler
from common.services.sqs_listener import get_sqs_listener
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(lifespan=lifespan)

app.add_middleware(RequestLoggerMiddleware)
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
app.include_router(chat_router)
app.include_router(chat_message_router)
app.include_router(ws_router)
# SDK router
app.include_router(per_router)
# Add exception handler for unhandled exceptions
app.add_exception_handler(Exception, unhandled_exceptions_handler)


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
