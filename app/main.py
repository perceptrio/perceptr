from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.org import router
# from database import engine, Base

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
app.include_router(router.router)

@app.get("/")
async def root():
    return {"message": "Hello World"}