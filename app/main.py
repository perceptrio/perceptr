from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.org.router import router as org_router
from api.v1.recording.router import router as recording_router
from api.v1.recording_intervals.router import router as recording_interval_router
from api.v1.issue.router import router as issue_router
from api.v1.analytics.router import router as analytics_router

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


@app.get("/")
async def root():
    return {"message": "Hello World"}
