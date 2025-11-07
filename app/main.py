"""FastAPI application entry point."""
# app/main.py
from __future__ import annotations
from contextlib import asynccontextmanager
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import AppInfo, get_settings
from app.core.database import Base, engine, init_engine, close_engine
from app.core.logging import get_logger, setup_logging
import app.models
from app.routers import get_api_router
from app.utils.errors import error_response

settings = get_settings()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Application startup", extra={"env": settings.app_env})
    await init_engine()
    try:
        yield
    finally:
        await close_engine()
        logger.info("Application shutdown", extra={"env": settings.app_env})

app_info = AppInfo()
app = FastAPI(title=app_info.name, version=app_info.version, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(get_api_router())

# ✅ Compatible avec les tests qui font app.router.startup()
@app.on_event("startup")
async def startup_event() -> None:
    await init_engine()                         # <-- IMPORTANT
    Base.metadata.create_all(bind=engine)
    logger.info("Tables ensured on startup", extra={"env": settings.app_env})

@app.on_event("shutdown")
async def shutdown_event() -> None:
    await close_engine()
    logger.info("Tables closed on shutdown", extra={"env": settings.app_env})

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(status_code=500, content=error_response("INTERNAL_SERVER_ERROR", "An unexpected error occurred."))

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    content: dict[str, Any] = detail if isinstance(detail, dict) and "error" in detail else error_response("HTTP_ERROR", str(detail))
    return JSONResponse(status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None))

__all__ = ["app"]

