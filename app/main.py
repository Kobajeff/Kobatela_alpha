"""FastAPI application entry point."""
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import models
from app.config import AppInfo, get_settings
from app.db import engine
from app.logging_conf import configure_logging
from app.routers import get_api_router
from app.utils.errors import error_response

configure_logging()
logger = logging.getLogger(__name__)

app_info = AppInfo()
app = FastAPI(title=app_info.name, version=app_info.version)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(get_api_router())


@app.on_event("startup")
def startup_event() -> None:
    """Run application startup tasks."""

    models.Base.metadata.create_all(bind=engine)
    settings = get_settings()
    logger.info("Application startup", extra={"env": settings.app_env})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle uncaught exceptions with standardized error payload."""

    logger.exception("Unhandled exception", exc_info=exc)
    payload = error_response("INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
    return JSONResponse(status_code=500, content=payload)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Ensure HTTP exceptions respect the error payload contract."""

    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        content: dict[str, Any] = detail
    else:
        content = error_response("HTTP_ERROR", str(detail))
    return JSONResponse(status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None))


__all__ = ["app"]
