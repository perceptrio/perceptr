from api.v1.analytics.router import router as analytics_router
from api.v1.issue.router import router as issue_router
from api.v1.org.router import router as org_router
from api.v1.per.router import router as per_router
from api.v1.recording.router import router as recording_router
from api.v1.recording_intervals.router import router as recording_interval_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

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
# SDK router
app.include_router(per_router)


@app.get("/health", response_model=dict[str, str])  # type: ignore
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_model=dict[str, str])  # type: ignore
async def root() -> dict[str, str]:
    return {"message": "Hello World"}
