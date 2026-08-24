"""
Banking Kiosk Backend — Module 4
FastAPI application entry point.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.middleware.error_handler import global_exception_handler
from app.routers import (
    biometrics,
    confirmation,
    session,
    teller,
    token_verify,
    voice_intent,
    ws_dashboard,
)
from app.services.redis_publisher import close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Banking Kiosk Backend starting up.")
    yield
    logger.info("Shutting down — closing Redis connection.")
    await close_redis()


app = FastAPI(
    title="Banking Kiosk Backend",
    description=(
        "Orchestration hub for the voice-assisted banking kiosk (Module 4). "
        "Receives from Voice AI and Biometrics; sends to Security and Staff Portal."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# Global exception → standard error envelope
app.add_exception_handler(Exception, global_exception_handler)

# ── REST routers ──────────────────────────────────────────────────────────────
PREFIX = "/api/v1"
app.include_router(voice_intent.router,  prefix=PREFIX, tags=["Voice AI"])
app.include_router(biometrics.router,    prefix=PREFIX, tags=["Biometrics"])
app.include_router(confirmation.router,  prefix=PREFIX, tags=["Confirmation"])
app.include_router(teller.router,        prefix=PREFIX, tags=["Teller"])
app.include_router(session.router,       prefix=PREFIX, tags=["Session"])
app.include_router(token_verify.router,  prefix=PREFIX, tags=["Token"])

# ── WebSocket router (no prefix — WS path is /ws/dashboard) ──────────────────
app.include_router(ws_dashboard.router, tags=["Dashboard WebSocket"])


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "service": "banking-kiosk-backend",
        "version": "0.1.0",
    }
