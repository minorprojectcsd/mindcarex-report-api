"""
SVC 2 — Session Report Generator
Run locally:  uvicorn main:app --reload --port 8001
Docker:       see Dockerfile
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.router   import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()   # creates session_reports table in Neon on first run
    yield


app = FastAPI(
    title="Session Report Service",
    version="1.0.0",
    description="Generates clinical reports from completed voice sessions using Groq LLaMA",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "svc2_report_generator"}
