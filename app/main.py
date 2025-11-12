from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import AppInfo, get_settings
from app import db  # moteur/metadata centralisés
from app.core.logging import get_logger, setup_logging
import app.models  # enregistre les tables
from app.routers import get_api_router
from app.utils.errors import error_response

settings = get_settings()
logger = get_logger(__name__)

# -------- Lifespan (nouveau mécanisme) --------
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Application startup", extra={"env": settings.app_env})
    if settings.psp_webhook_secret is None:
        raise RuntimeError("PSP_WEBHOOK_SECRET manquant : configurez la variable d'environnement ou le fichier .env")
    db.init_engine()  # sync, idempotent
    # IMPORTANT : créer les tables ici quand on utilise lifespan
    db.create_all()
    try:
        yield
    finally:
        db.close_engine()
        logger.info("Application shutdown", extra={"env": settings.app_env})

app_info = AppInfo()

app = FastAPI(title=app_info.name, version=app_info.version, lifespan=lifespan)

# Middleware & routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(get_api_router())

# Handlers d’erreurs
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    payload = error_response("INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
    return JSONResponse(status_code=500, content=payload)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        content: dict[str, Any] = detail
    else:
        content = error_response("HTTP_ERROR", str(detail))
    return JSONResponse(status_code=exc.status_code, content=content, headers=getattr(exc, "headers", None))

__all__ = ["app"]
