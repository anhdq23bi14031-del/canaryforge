"""
CanaryForge - Self-hosted honeypot & canary token platform
"""
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.api.tokens import router as tokens_router
from backend.api.alerts import router as alerts_router
from backend.api.dashboard import router as dashboard_router
from backend.capture.server import router as capture_router
from backend.config import settings
from backend.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="CanaryForge",
    description="Self-hosted honeypot and canary token platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tokens_router, prefix="/api/tokens", tags=["tokens"])
app.include_router(alerts_router, prefix="/api/alerts", tags=["alerts"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(capture_router, prefix="/c", tags=["capture"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "CanaryForge"}


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
