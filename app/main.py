from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db  # moteur/metadata centralisés
from app.config import AppInfo, SCHEDULER_ENABLED, get_settings
from app.core.logging import get_logger, setup_logging
import app.models  # enregistre les tables
from app.routers import apikeys, get_api_router
from app.services.cron import expire_mandates_once
from app.utils.errors import error_response

settings = get_settings()
logger = get_logger(__name__)
scheduler: AsyncIOScheduler | None = None

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
    # NOTE: In multi-replica deployments, enable SCHEDULER_ENABLED=true on ONE runner only (others=false).
    # For 1.0.0 consider external cron/worker or APScheduler with a distributed job store/lock.
    if SCHEDULER_ENABLED:
        global scheduler
        scheduler = AsyncIOScheduler()
        scheduler.start()
        scheduler.add_job(
            expire_mandates_once,
            "interval",
            minutes=60,
            id="expire-mandates",
            replace_existing=True,
        )
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        db.close_engine()
        logger.info("Application shutdown", extra={"env": settings.app_env})

app_info = AppInfo()

app = FastAPI(title=app_info.name, version=app_info.version, lifespan=lifespan)

# Middleware & routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

if settings.PROMETHEUS_ENABLED:
    from starlette_exporter import PrometheusMiddleware, handle_metrics

    app.add_middleware(PrometheusMiddleware)
    app.add_route("/metrics", handle_metrics)

if settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.2)
app.include_router(get_api_router())
app.include_router(apikeys.router)

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
